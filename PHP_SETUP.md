# PHP Backend Setup — Ratholes Feature

The bot's `cogs/ratholes.py` needs 4 new PHP endpoints and 1 MySQL table
on your existing `t-doc.co.za/discord/` backend. Drop the SQL into your
database, the 4 files into your `/discord/` folder, and you're done.

---

## 1. MySQL table

Run this once against the same database your other endpoints already use:

```sql
CREATE TABLE IF NOT EXISTS ratholes (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    server       VARCHAR(16)  NOT NULL,
    rathole_name VARCHAR(255) NOT NULL,
    description  TEXT         NULL,
    image_url    VARCHAR(1000) NULL,
    created_by   VARCHAR(64)  NULL,
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_server_name (server, rathole_name),
    INDEX idx_server (server)
);
```

The `UNIQUE KEY (server, rathole_name)` lets `/rathole_edit` and
`/rathole_delete` target a rathole by (server, name) without needing IDs.

---

## 2. PHP endpoints

All four files use the same key-check pattern as your existing endpoints.
Adjust `$SECRET_KEY` and your DB credentials to match what the rest of
`/discord/*.php` already uses (or extract to a shared `db.php`).

### `/discord/ratholes.php`

```php
<?php
header('Content-Type: application/json');

$SECRET_KEY = "SUPER_SECRET_KEY";  // must match Railway API_KEY

if (($_GET["key"] ?? "") !== $SECRET_KEY) { http_response_code(401); echo "[]"; exit; }

$conn = new mysqli("localhost", "DB_USER", "DB_PASS", "DB_NAME");
if ($conn->connect_error) { echo "[]"; exit; }

$server = $_GET["server"] ?? "";
if ($server === "") { echo "[]"; exit; }

$stmt = $conn->prepare(
    "SELECT id, server, rathole_name, description, image_url, created_by, created_at
     FROM ratholes WHERE server = ? ORDER BY rathole_name ASC"
);
$stmt->bind_param("s", $server);
$stmt->execute();
$result = $stmt->get_result();

$out = [];
while ($row = $result->fetch_assoc()) { $out[] = $row; }

echo json_encode($out);
```

### `/discord/add_rathole.php`

```php
<?php
header('Content-Type: application/json');

$SECRET_KEY = "SUPER_SECRET_KEY";
if (($_GET["key"] ?? "") !== $SECRET_KEY) { http_response_code(401); echo "[]"; exit; }

$conn = new mysqli("localhost", "DB_USER", "DB_PASS", "DB_NAME");
if ($conn->connect_error) { echo "[]"; exit; }

$server       = $_GET["server"]       ?? "";
$name         = $_GET["rathole_name"] ?? "";
$description  = $_GET["description"]  ?? "";
$image_url    = $_GET["image_url"]    ?? null;
$created_by   = $_GET["created_by"]   ?? null;

if ($server === "" || $name === "") { echo '{"error":"missing server or name"}'; exit; }

// Upsert (same server+name updates existing).
$stmt = $conn->prepare(
    "INSERT INTO ratholes (server, rathole_name, description, image_url, created_by)
     VALUES (?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE
        description = VALUES(description),
        image_url   = COALESCE(VALUES(image_url), image_url),
        updated_at  = CURRENT_TIMESTAMP"
);
$stmt->bind_param("sssss", $server, $name, $description, $image_url, $created_by);
$stmt->execute();

echo '{"ok":true}';
```

### `/discord/update_rathole.php`

```php
<?php
header('Content-Type: application/json');

$SECRET_KEY = "SUPER_SECRET_KEY";
if (($_GET["key"] ?? "") !== $SECRET_KEY) { http_response_code(401); echo "[]"; exit; }

$conn = new mysqli("localhost", "DB_USER", "DB_PASS", "DB_NAME");
if ($conn->connect_error) { echo "[]"; exit; }

$server = $_GET["server"]       ?? "";
$name   = $_GET["rathole_name"] ?? "";
if ($server === "" || $name === "") { echo '{"error":"missing server or name"}'; exit; }

// Only update fields that were supplied.
$updates = [];
$params  = [];
$types   = "";

if (array_key_exists("description", $_GET)) {
    $updates[] = "description = ?";
    $params[]  = $_GET["description"];
    $types    .= "s";
}
if (array_key_exists("image_url", $_GET)) {
    $updates[] = "image_url = ?";
    $params[]  = $_GET["image_url"];
    $types    .= "s";
}

if (empty($updates)) { echo '{"ok":true,"noop":true}'; exit; }

$params[] = $server;
$params[] = $name;
$types   .= "ss";

$sql = "UPDATE ratholes SET " . implode(", ", $updates) .
       " WHERE server = ? AND rathole_name = ?";

$stmt = $conn->prepare($sql);
$stmt->bind_param($types, ...$params);
$stmt->execute();

echo '{"ok":true}';
```

### `/discord/delete_rathole.php`

```php
<?php
header('Content-Type: application/json');

$SECRET_KEY = "SUPER_SECRET_KEY";
if (($_GET["key"] ?? "") !== $SECRET_KEY) { http_response_code(401); echo "[]"; exit; }

$conn = new mysqli("localhost", "DB_USER", "DB_PASS", "DB_NAME");
if ($conn->connect_error) { echo "[]"; exit; }

$server = $_GET["server"]       ?? "";
$name   = $_GET["rathole_name"] ?? "";
if ($server === "" || $name === "") { echo '{"error":"missing server or name"}'; exit; }

$stmt = $conn->prepare(
    "DELETE FROM ratholes WHERE server = ? AND rathole_name = ?"
);
$stmt->bind_param("ss", $server, $name);
$stmt->execute();

echo '{"ok":true}';
```

---

## 3. Test manually

After uploading, hit each endpoint from a browser (replace `SUPER_SECRET_KEY`):

```
https://www.t-doc.co.za/discord/ratholes.php?key=SUPER_SECRET_KEY&server=2491
```

Should return `[]` at first. After adding a rathole through the bot, it
should return that record.

---

## 4. Usage in Discord

- `/rathole_add server:2491 name:"Blue Ob" description:"Behind the rock next to swamp" image:<attach a screenshot>`
- `/rathole_edit server:2491 name:"Blue Ob" image:<new screenshot>`
- `/rathole_delete server:2491 name:"Blue Ob"`
- **Server menu → Ratholes button** → paginated view of all ratholes for that server, with images embedded.

## Notes on image persistence

Discord attachment URLs are signed and can expire after ~24h if they are
never re-embedded by a bot. Because the bot re-embeds them on every view
(via `embed.set_image(url=...)`), Discord auto-renews them and they stay
usable in practice. If you ever need bullet-proof image storage, consider:

- Re-uploading the attachment to a dedicated "rathole storage" Discord
  channel and storing the resulting message id, then fetching that
  message and reading its attachment URL on demand, OR
- Uploading to an external host (Imgur, S3, Cloudinary) and storing that
  URL instead.

Both are drop-in additions later — no schema change needed.
