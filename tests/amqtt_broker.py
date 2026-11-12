"""A small real MQTT broker (amqtt) for the integration tests.  Usage: python tests/amqtt_broker.py PORT"""
import asyncio
import logging
import sys

from amqtt.broker import Broker

logging.disable(logging.CRITICAL)


async def main(port: int):
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
        "sys_interval": 0,
        "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
        "topic-check": {"enabled": False},
    })
    await broker.start()
    print("READY", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
