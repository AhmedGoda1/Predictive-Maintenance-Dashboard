# Logins: admin and maintenance

The dashboard has two kinds of users. Which page someone sees depends on the account they log in with.

| Role          | Sees                                                                                         |
|---------------|----------------------------------------------------------------------------------------------|
| `admin`       | The full dashboard: fleet overview, asset detail, dispatching work orders, live data controls. |
| `maintenance` | Only the open work orders, with **Start work**, **Complete** and **Reject** buttons.          |

A work order is *open* until it is completed, cancelled or rejected, either by a technician on this page or by
the maintenance service (see [WORK_ORDERS.md](WORK_ORDERS.md)). Most urgent first, then oldest first. A
technician's button press is recorded exactly like a confirmation from the service, with the technician's name
and optional note, so the admin sees it on the alert in the asset view.

## Set up the accounts

Accounts live in the app's secrets, never in the repository.

1. Make a password hash for each account (the password is asked for and not shown):

   ```bash
   python scripts/hash_password.py
   ```

2. Add the accounts to the secrets.
   *On Streamlit Cloud:* *Manage app → Settings → Secrets*.
   *Locally:* `.streamlit/secrets.toml` in the folder you run `streamlit` from (it is in `.gitignore`).

   ```toml
   [users.ahmed]
   password = "pbkdf2_sha256$600000$...$..."    # the line printed in step 1
   role = "admin"

   [users.technician]
   password = "pbkdf2_sha256$600000$...$..."
   role = "maintenance"
   ```

   Add as many `[users.<name>]` sections as you need; the name after `users.` is the username. A plain-text
   `password = "..."` works too, but then anyone who can read the secrets can read the password.

3. Save. The next page load asks for a login. **Log out** is at the top of the sidebar.

## Good to know

- **No `[users]` in the secrets means no login**: everyone sees the full dashboard, as before, and the sidebar
  says so. Set up at least one admin account before sharing the hosted app's link.
- Removing an account or changing its role in the secrets takes effect on that person's next click.
- An account with any role other than `admin` or `maintenance` cannot log in.
- This is a simple shared-secrets login for a small team: no password reset, no lockout after repeated failures
  (each wrong attempt waits one second), and passwords are changed by editing the secrets.
  For a company single sign-on (Google, Microsoft Entra, Okta), Streamlit's built-in `st.login` is the next step.
