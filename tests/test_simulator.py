import time

import pytest

from pdm import db, ingest, simulator


def run_to_end(feed, timeout=60):
    feed.run()                                    # blocking, no thread
    assert feed.status()["done"], feed.status()


def test_engine_selection_spreads_the_remaining_life_and_avoids_the_recorded_fleet():
    units = simulator.pick_engines(4)
    assert len(set(units)) == 4 and all((u - 1) % simulator.OFFLINE_FLEET_STRIDE for u in units)
    feeds = simulator.build_feeds(4)
    ends = sorted(f.run.rul_true()[-1] for f in feeds)
    assert ends[0] < 25 and ends[-1] > 90                                       # some will turn Critical, some will not
    assert all(f.asset_id.startswith(simulator.LIVE_PREFIX) for f in feeds)


def test_payload_looks_like_what_a_gateway_sends():
    feed = simulator.build_feeds(1)[0]
    from datetime import datetime
    rows = simulator.payload(feed, 0, 3, datetime(2024, 1, 1))
    assert [r["age"] for r in rows] == [1.0, 2.0, 3.0]
    assert rows[1]["ts"] > rows[0]["ts"] and "s11" in rows[0]["values"]
    assert all(isinstance(v, float) for v in rows[0]["values"].values())


def test_local_feed_streams_engines_through_ingestion_and_scores_them(live_db):
    feeds = simulator.build_feeds(2)
    feed = simulator.LiveFeed(feeds, simulator.LocalSink(live_db), interval_s=0, step=40)
    run_to_end(feed)
    for f in feeds:
        assert len(db.get_series(f.asset_id, live_db)) == f.total
        state = ingest.asset_state(f.asset_id, live_db)
        assert state["method"] == "learned" and state["status"] != "Learning"
        assert db.get_asset(f.asset_id, live_db)["metadata"]["live"] is True
        assert state["rul_low"] <= state["rul"] <= state["rul_high"]


def test_motor_feed_reports_the_breakdown_at_the_end(live_db):
    feed = simulator.LiveFeed(simulator.build_feeds(0, include_motor=True), simulator.LocalSink(live_db),
                              interval_s=0, step=200)
    run_to_end(feed)
    state = ingest.asset_state("LIVE-MTR-01", live_db)
    assert state["status"] == "Failed" and db.get_failure("LIVE-MTR-01", live_db)["observed"] == 1


def test_restarting_the_feed_starts_the_assets_over(live_db):
    sink = simulator.LocalSink(live_db)
    simulator.LiveFeed(simulator.build_feeds(1), sink, interval_s=0, step=60).run()
    first = simulator.build_feeds(1)[0].asset_id
    assert len(db.get_series(first, live_db)) > 0
    feed = simulator.LiveFeed(simulator.build_feeds(1), sink, interval_s=0, step=10)
    feed.sent  # a fresh feed has sent nothing yet
    feed._stop.set()                              # register (and reset) only, then stop before streaming
    feed.run()
    assert db.get_series(first, live_db).empty


def test_reset_removes_only_simulated_assets(live_db):
    ingest.register_asset("REAL-1", "turbofan_engine", db_path=live_db)
    simulator.LiveFeed(simulator.build_feeds(2), simulator.LocalSink(live_db), interval_s=0, step=30).run()
    assert simulator.reset_live_assets(live_db) == 2
    assert list(db.list_assets(db_path=live_db)["asset_id"]) == ["REAL-1"]


def test_a_failing_sink_is_counted_not_fatal(live_db):
    class Flaky(simulator.LocalSink):
        calls = 0

        def send(self, asset_id, readings):
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise RuntimeError("network down")
            return super().send(asset_id, readings)

    feed = simulator.LiveFeed(simulator.build_feeds(1), Flaky(live_db), interval_s=0, step=100)
    run_to_end(feed)
    assert feed.errors == 1 and "network down" in feed.last_error                # the batch was retried on the next tick
    assert len(db.get_series(simulator.build_feeds(1)[0].asset_id, live_db)) == simulator.build_feeds(1)[0].total


def test_feed_runs_in_a_background_thread_and_can_be_stopped(live_db):
    feed = simulator.LiveFeed(simulator.build_feeds(1), simulator.LocalSink(live_db), interval_s=0.05, step=1).start()
    time.sleep(0.6)
    assert feed.running
    feed.stop()
    time.sleep(0.4)
    assert not feed.running and 0 < sum(feed.sent.values()) < simulator.build_feeds(1)[0].total


def test_timestamps_keep_increasing_when_batches_follow_each_other_immediately(live_db):
    """Big batches sent back to back used to overlap in time and the later one was refused as out of order."""
    sink = simulator.LocalSink(live_db)
    feeds = simulator.build_feeds(1)
    rejected = []
    original = sink.send
    sink.send = lambda a, r: (lambda out: (rejected.extend(out["rejected"]), out)[1])(original(a, r))
    simulator.LiveFeed(feeds, sink, interval_s=0, step=60).run()
    assert not rejected and len(db.get_series(feeds[0].asset_id, live_db)) == feeds[0].total
