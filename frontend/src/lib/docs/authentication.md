# Authentication

The Storywrangler API uses **API key authentication**. Accounts are created by an admin — you cannot self-register. Once your account exists, you exchange your credentials for an API key and use it as a Bearer token on all authenticated requests.

## Get your API key

Once your account exists, POST your credentials to `/auth/login`. The response includes your permanent `api_key`.

```bash
curl -X POST https://api.storywrangler.uvm.edu/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username": "alice", "password": "secret"}'
```

Response:

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@uvm.edu",
  "role": "user",
  "api_key": "sk_abc123...",
  "is_active": true
}
```

Save your `api_key` — this is the token you'll use for every subsequent request.

## Use your API key

Pass the key as a Bearer token in the `Authorization` header:

```bash
curl https://api.storywrangler.uvm.edu/auth/me \
  -H 'Authorization: Bearer sk_abc123...'
```

With the SDK:

```python
from storywrangler import Storywrangler

client = Storywrangler(api_key="sk_abc123...")
client.registry.register(dataset)
```

## Roles

| Role | What it can do |
| --- | --- |
| `user` | Register and update datasets. Query all public endpoints. |
| `admin` | Everything a `user` can do, plus create accounts, manage roles, and access `/admin/*` endpoints. |

## Admin bootstrap

A single admin account is seeded automatically on first server startup using environment variables:

```bash
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
ADMIN_EMAIL=admin@example.com
```

The generated API key is printed to the server log on first boot. Use it to provision the first real accounts.

## Verify your token

```bash
curl https://api.storywrangler.uvm.edu/auth/me \
  -H 'Authorization: Bearer <your-api-key>'
```

Returns your user profile, or `401 Unauthorized` if the key is invalid or your account has been deactivated.
