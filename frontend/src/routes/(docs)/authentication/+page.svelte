<script lang="ts">
	import { Snippet } from '$lib/components/ui/snippet';
</script>

<h1>Authentication</h1>

<p>
	The Storywrangler API uses <strong>API key authentication</strong>. Accounts are created by an
	admin — you cannot self-register. Once your account exists, you exchange your credentials for an
	API key and use it as a Bearer token on all authenticated requests.
</p>

<h2>Get your API key</h2>

<p>
	Once your account exists, POST your credentials to <code>/auth/login</code>. The response
	includes your permanent <code>api_key</code>.
</p>

<Snippet text={`curl -X POST http://localhost:8000/auth/login \\
  -H 'Content-Type: application/json' \\
  -d '{"username": "alice", "password": "secret"}'`} />

<p>Response:</p>

<Snippet text={`{
  "id": 1,
  "username": "alice",
  "email": "alice@uvm.edu",
  "role": "user",
  "api_key": "sk_abc123...",
  "is_active": true
}`} />

<p>Save your <code>api_key</code> — this is the token you'll use for every subsequent request.</p>

<h2>Use your API key</h2>

<p>Pass the key as a Bearer token in the <code>Authorization</code> header:</p>

<Snippet text={`curl http://localhost:8000/auth/me \\
  -H 'Authorization: Bearer sk_abc123...'`} />

<p>With the SDK:</p>

<Snippet text={`from storywrangler import StorywranglerClient

client = StorywranglerClient(api_key="sk_abc123...")
client.register(dataset)`} />

<h2>Roles</h2>

<table>
	<thead>
		<tr>
			<th>Role</th>
			<th>What it can do</th>
		</tr>
	</thead>
	<tbody>
		<tr>
			<td><code>user</code></td>
			<td>Register and update datasets. Query all public endpoints.</td>
		</tr>
		<tr>
			<td><code>admin</code></td>
			<td>
				Everything a <code>user</code> can do, plus create accounts, manage roles, and access
				<code>/admin/*</code> endpoints.
			</td>
		</tr>
	</tbody>
</table>

<h2>Admin bootstrap</h2>

<p>
	A single admin account is seeded automatically on first server startup using environment
	variables:
</p>

<Snippet text={`ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
ADMIN_EMAIL=admin@example.com`} />

<p>
	The generated API key is printed to the server log on first boot. Use it to provision the first
	real accounts.
</p>

<h2>Verify your token</h2>

<Snippet text={`curl http://localhost:8000/auth/me \\
  -H 'Authorization: Bearer <your-api-key>'`} />

<p>
	Returns your user profile, or <code>401 Unauthorized</code> if the key is invalid or your
	account has been deactivated.
</p>
