# Smail — V1

[Version française](README.md)

**Version 1.0.0 — first public release.** A desktop email client for Windows, available in French and English, built in Python with PySide6.

V1 offers three interface styles, light and dark themes, a unified inbox, a compose window with attachment thumbnails, and a reading pane organized into cards. Appearance settings are in the **View** menu. Details of this release are in [CHANGELOG.md](CHANGELOG.md).

Desktop client in French and English, Python 3.11+ and PySide6, with all four phases of the specification implemented. IMAP handles receiving and message actions; SMTP handles sending. No account credentials or OAuth application IDs ship with the project.

The interface language is chosen in **Settings › General** (Automatic — follows Windows / Français / English) and is applied on restart.

## Install and run

In PowerShell:

```powershell
git clone https://github.com/Smeth/smail.git
cd smail
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m mailclient.main
```

To update an existing install, close Smail, rerun the dependency install command, then the launch command. Existing accounts remain compatible and new SQLite tables are created automatically. You don't need to activate the virtual environment or change the PowerShell execution policy.

The built executable is `dist\Smail\Smail.exe`. Keep and distribute the **entire** `dist\Smail` folder: the exe alone is not enough, notably for WebEngine.

To distribute Smail, prefer the `Smail-<version>-installation.exe` installer, produced by continuous integration (or locally with Inno Setup 6: `ISCC.exe /DAppVersion=1.0.0 installer\Smail.iss` after PyInstaller). It installs Smail for the current user, without administrator rights, in `%LOCALAPPDATA%\Programs\Smail`, with a Start menu shortcut. Uninstalling keeps accounts, cache and secrets: remove your accounts in Smail first to erase everything. The installer is not signed: Windows SmartScreen may show a warning until a code-signing certificate is used.

## Accounts and network encryption

**Add account** lets you enter the name, address and separate IMAP/SMTP settings. When you leave the address field, Gmail, Outlook/Hotmail and Yahoo domains prefill any server fields that are still empty. For LWS, cPanel or an internal server, use the values provided by your host or administrator. The **Account** button edits an existing account, its signature and its authentication.

**Accounts › Delete account…** (or the trash icon in Settings › Accounts) removes the account from this PC after confirmation: settings, offline cache, local drafts, local copies of sent mail, trusted certificates, and the password and OAuth2 tokens stored in Windows Credential Manager. Messages remain on the server. Close any open compose windows first.

| Connection | Usual IMAP port | Usual SMTP port | Behavior |
| --- | --- | --- | --- |
| SSL/TLS | 993 | 465 | Immediate TLS, default choice |
| STARTTLS | 143 | 587 | Mandatory encrypted upgrade before authentication |
| None | 143 | 25 | Plaintext connection after explicit confirmation |

Changing the type fills in the usual port; the port remains editable. **None** shows a red warning and requires you to check the risk confirmation before testing or saving. An open padlock and a warning stay visible next to the account. This mode exposes credentials and mail to third parties on the network; some servers refuse this authentication. OAuth2 requires an encrypted connection on both servers.

**Test IMAP and SMTP connection** authenticates to both servers without sending a message. The login defaults to the email address. If your host provides a different login (for example “client12345”) or an outgoing server with its own credentials, fill in the **Username** field in the IMAP or SMTP block and, if needed, uncheck **SMTP password same as account password** to enter a separate SMTP password (stored in Windows Credential Manager). These credentials are stored separately from the account configuration, which remains readable by Smail 1.0.0. With OAuth2, the identity is always the email address. Display names and subjects may contain accented characters; mailbox addresses must be ASCII.

System TLS verification and server name checking are on by default (`ssl.create_default_context`). If verification fails, an unauthenticated probe retrieves the certificate. The security dialog shows the server, issuer, dates, SHA-256 fingerprint and the reason for the failure. **Cancel** is the default choice. **Continue anyway** only allows that fingerprint for this account and server for the current session. The permanent-trust checkbox stores the fingerprint in SQLite. Any fingerprint change shows the alert again, even if the new certificate is otherwise valid. Compare the fingerprint with your administrator over an independent channel before trusting it.

A server without STARTTLS is refused without sending credentials: there is no automatic fallback to plaintext. A certificate alert encountered during sync suspends that operation; select the account and then **Refresh** to review the alert. Then run **Sync** again; IDLE monitoring can be restarted by turning its option off and on again in Settings. To remove a permanent exception, open **Settings › Security › Trusted certificates** and click **Remove**: the alert will reappear the next time you connect to that server.

## Gmail: app password

Turn on 2-Step Verification for your Google account, then create an app password dedicated to Smail. Enter that password in Smail instead of your main password. The option may be unavailable depending on your organization’s policy or the account’s security settings. See [Google’s instructions](https://support.google.com/accounts/answer/185833?hl=fr).

Gmail can also use OAuth2 with the configuration below. The Gmail server automatically keeps a copy of sent messages; Smail skips the extra APPEND to avoid creating a duplicate.

## Google and Microsoft OAuth2

The flow is implemented: system browser, authorization code, PKCE S256, `state` verification, HTTP callback limited to the local loopback, token refresh, and IMAP/SMTP XOAUTH2 authentication. No mail-reading browser is used for sign-in. Tokens, refresh tokens and the Google client secret are stored exclusively in Windows Credential Manager, via keyring. Long tokens are split across several vault entries to respect the Windows limit; no fragment is ever written to a file.

You need an **application registered with the provider**. The project cannot create that registration in your account and contains no shared client ID.

### Google

1. In Google Cloud, configure the OAuth consent screen and an OAuth client of type **Desktop app**. Add your account to the test users if the app is in testing mode. The mail access scope is `https://mail.google.com/`; public distribution may require Google verification of this restricted scope.
2. In **Account**, select **Google OAuth2** and enter the client ID and, if required, the client secret issued for this desktop client.
3. Click **Connect with OAuth2 in the browser** and authorize the account matching the address entered in Smail. The callback uses `http://127.0.0.1:<port-libre>/callback`.
4. Test the servers, then save the account. Refresh is automatic as long as the provider honors the refresh token.

See [Google’s documentation for desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app).

### Microsoft / Outlook / Microsoft 365

1. Register a public native application in Microsoft Entra. Choose the expected account types (include personal accounts for Outlook.com).
2. Add a redirect of type **Mobile and desktop applications**: `http://localhost/callback`. Smail listens only on `127.0.0.1`, on a free port; Microsoft ignores the port when matching a localhost redirect.
3. Add the Exchange Online **delegated** permissions `IMAP.AccessAsUser.All` and `SMTP.Send`, plus the consent required for `offline_access`. Your organization may require admin consent or restrict IMAP/SMTP AUTH. These are not the Microsoft Graph `Mail.*` permissions.
4. In Smail, select **Microsoft OAuth2** and enter the client ID. The tenant defaults to `common`; for a single-tenant app, enter the tenant UUID or domain. No confidential client secret is requested for this public client.
5. Sign in in the browser, test IMAP/SMTP, then save.

References: [OAuth for Microsoft IMAP/SMTP](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth) and [localhost redirects](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url). Availability also depends on account and tenant permissions. Changing the client ID, tenant or address requires authorizing again.

## Reading, searching and managing messages

The interface provides folders, a message list paged by 50, and the reading pane. Descending UIDs give the order of arrival; the unified view uses the messages’ declared dates. Unread messages are bold; starred messages and attachments have an indicator.

- Select a message to read it as plain text or sanitized HTML. MIME, UTF-8, ISO-8859-1, quoted-printable and base64 encodings are decoded. Reading uses `BODY.PEEK` and does not change the read/unread flag.
- **Conversation view** (View › Group by conversation, Ctrl+Shift+T, on by default): messages in the same discussion are combined on one line based on Message-ID, In-Reply-To and References (never mixing two accounts; falls back to the subject for “Re:” replies without references). The line shows the participants and the number of messages on the page, and stays bold while any message is unread. When opened, the reader shows the first unread message, otherwise the most recent, in a stacked view: earlier messages are collapsed above (sender, date and snippet), later ones below, including your replies found in Sent and other cached folders. Click a collapsed message or use Alt+Down / Alt+Up to expand it. Snippets skip quotes and signatures; they are computed during sync and kept in the cache. Archive, Delete, Move, Read / unread and Star apply to the whole conversation in the list; Reply targets the displayed message. Grouping covers the loaded page (50 messages).
- Ctrl+click, Shift+click or Ctrl+A select multiple messages. **Read / unread**, **Star**, **Move**, **Archive** and **Delete** act on the whole selection, including from the unified inbox (Move requires messages from a single account); a single IMAP command is sent per folder. Reply and Forward require a single message. Delete moves to Trash after confirmation; from Trash, Delete becomes a **permanent deletion**, confirmed separately.
- **Mark all as read** (Ctrl+Shift+U, Message menu, or right-click on a folder) acts on the whole current folder on the server, or on each account’s Inbox in the unified inbox.
- **Accounts › Folder** (or right-click on the folder list) creates, renames or deletes a folder. System folders (Inbox, Sent, Drafts, Trash, Junk) are protected. For a subfolder, use your server’s separator (often `/` or `.`). **Empty folder…** permanently deletes everything in Trash or Junk.
- Actions check UIDVALIDITY to avoid changing a different message after a folder has been recreated. Move uses UID MOVE when available, otherwise COPY followed by a targeted deletion of the source. Without UIDPLUS, the source stays flagged `Deleted` (hidden) until the server purges it; Smail only runs a global purge (EXPUNGE) when you empty Trash or Junk entirely.
- **Advanced search**: combine operators (French or English) — `from:`, `to:`, `subject:`, `has:attachment`, `is:unread`, `is:read`, `is:starred`, `after:` / `before:` with a date `2026-11-01` or `01/11/2026` (`before:` excludes the given day) — with words or `"exact phrases"` searched across the whole message; all criteria must match. The French operators (`de:`, `à:`, `objet:`, `a:pj`, `est:nonlu`, `est:lu`, `est:étoilé`, `après:`, `avant:`) work too. Online, the search is translated into IMAP SEARCH commands; each accented text goes in its own command (UTF-8 literal, never interpolated) and the results are intersected. `has:attachment` is checked against the message structure (5,000 messages at most). Offline and in the unified inbox, the same criteria apply to the cache. The **This folder / All folders** list extends the search to all of the account’s folders (the 100 most recent results, with their source folder).
- Type a search and press **Enter**. Online, IMAP TEXT searches the whole folder with a literal UTF-8 value. Offline, and in the unified inbox, the search covers metadata and content already in the cache. The banner shows this scope. If cache encryption is off, a SQLite full-text index (FTS5) speeds up this search from three characters; it contains message text, just like the unencrypted cache itself. Turning on encryption deletes this index, and offline search then scans the decrypted cache. If the server refuses the search, the available cache is used and this is indicated.

HTML is sanitized against an allowlist with Bleach. Scripts, iframes, forms, JavaScript events and the message’s styles are stripped. JavaScript, external navigation, local file access and WebEngine downloads are blocked; a CSP and a network interceptor reinforce these rules. The WebEngine profile is private and in memory. Documents are served to WebEngine through an internal in-memory protocol, with no temporary file and without the `setHtml` data URL limit.

Remote images are blocked until you click **Show images**. This click allows only the HTTP/HTTPS images of the current message; it may tell the sender you read it. The next message restores blocking. Embedded PNG/JPEG/GIF/WebP images referenced by Content-ID need no network. Links are inactive, and sanitizing may simplify the layout.

**Preview** (button or double-click on an attachment): images and PDFs are shown inside Smail, with no external program or temporary file; text files (including HTML, XML, CSV, calendar) are shown as raw source, never interpreted, up to 2 MB. Executable or active files are never previewed.

**Calendar invitations**: a message containing an invitation (`text/calendar` or `.ics`) shows its title, date in local time, location and organizer. **Accept**, **Tentative** or **Decline** sends the organizer, after confirmation, a standard iTIP reply (`METHOD:REPLY`) understood by Outlook, Google Calendar and Thunderbird; a copy goes to Sent. **Add to calendar** opens the invitation in the Windows calendar app (via a temporary, unencrypted `.ics` file). A cancellation (`METHOD:CANCEL`) is flagged without a reply button. Smail does not manage a calendar. Time zones are converted using the `tzdata` package and the most common Outlook Windows time zone names; an unknown time zone is shown as is, with its name.

**Open in a window** (double-click on a message, or Ctrl+O) shows the message in its own window, with the same isolated reader; Reply, Reply all and Forward remain available there, while filing is done from the list. **Print…** (Ctrl+P) prints the header and sanitized body, without remote images; choose the “Microsoft Print to PDF” printer to get a PDF. Selected messages can be **dragged onto a folder** in the sidebar to move them there (not in the unified inbox or offline).

Attachments are never opened automatically. Select one, then **Save attachment…**. Names are sanitized for Windows; executables, scripts and certain active formats show an extra warning with Cancel as the default. Files you explicitly save are not protected by cache encryption.

## Composing and sending

**Compose**, **Reply**, **Reply all** and **Forward** open a window with account selection, To/Cc/Bcc, subject, body and attachments. Reply honors Reply-To; Reply all removes your own address and duplicates. Thread headers are preserved. Forwarding includes attachments. The account signature is added to the message; if you change accounts in an open compose window, check the signature manually.

**Formatting**: the toolbar above the body applies bold (Ctrl+B), italic (Ctrl+I), underline (Ctrl+U), bulleted or numbered lists, links (Ctrl+Shift+K; https, http or email address only) and clear formatting. A formatted message is sent as HTML with an equivalent plain-text part (lists and link addresses preserved); without formatting, it stays plain text. The HTML sent is rebuilt by Smail from a closed set of tags: content pasted from a web page or word processor is reduced to that set (styles, scripts and remote images dropped). Drafts keep their formatting.

**Formatted signature**: in **Account**, the signature accepts the same formatting (no images). It is inserted above the quoted text in replies. Its formatted version is stored in the account’s cache (encrypted with it); the account configuration keeps a plain-text version, used for clients without HTML.

**Background sending and undo**: after **Send**, the compose window closes immediately and the message is sent in the background. At the bottom of the main window, “Sending “Subject” in 8 s” offers **Undo** during the undo delay (10 s by default, adjustable from 0 to 30 s in Settings › Compose): the message then reopens as a draft. The actual progress is then shown: connecting, sending data (MB sent), server verification (often its antivirus), copying to Sent. Messages are sent one at a time; offline, they wait for the connection to return. Quitting Smail during the delay sends the message before closing. A failed or uncertain send is reported and kept in **File › Scheduled send** (never resent automatically); “Edit…” reopens it. Addresses are validated before the delay.

**Send later** (clock button): quick choices (in 1 hour, tomorrow 8 AM, Monday 8 AM) or a custom date. The message waits in a local outbox, encrypted with the cache; **File › Scheduled send…** lets you edit it (it becomes a draft again) or delete it. Smail must be open at the scheduled time; otherwise, the message is sent at the next startup. As with an immediate send, a failure is never resent automatically: it stays visible with its cause. An interrupted send (Smail closed abruptly during the SMTP connection) goes to the “uncertain” state: check your Sent folder before reopening it.

The To, Cc and Bcc fields suggest known addresses as you type: senders seen during sync (excluding Junk) and recipients of your sent mail, the latter first. The address book is stored per account in the cache: it is encrypted with it and deleted with the account.

Headers and addresses are validated; CR/LF control characters are forbidden. Bcc recipients appear in the SMTP envelope, never in the transmitted message or its saved copy. SMTP is never retried automatically after an error: a disconnection after DATA can leave delivery uncertain. Check delivery before trying again. On partial acceptance, only the rejected recipients stay in the draft; accepted recipients are not automatically included in a new send.

Local drafts are saved in the background after 1.5 seconds of inactivity and periodically while composing. Closing the window or pressing Esc waits for the save. **Local drafts** lets you resume them after a restart; **Delete draft** removes one after confirmation. **Copy to server drafts** creates an explicit copy on the server, even for a draft with no recipient; each click creates a new copy. Automatic local saving remains available without a network.

After SMTP acceptance, a local copy is kept in **Local Sent**. For servers other than Gmail, Smail also tries to keep a copy in the Sent folder. The SMTP send and this copy are two separate tasks: a copy error or a certificate alert never resends the message. **Export .eml** saves the open local copy. If the server already keeps a copy itself, a second server copy may appear (the Gmail case is handled automatically).

Shortcuts: Ctrl+N compose, Ctrl+R reply, Ctrl+Shift+R reply all, Ctrl+L forward, Del move to Trash, Ctrl+Shift+U mark all as read, F5 sync.

## Rules, junk mail and unsubscribing

**Settings › Rules and junk** brings together sorting rules and blocked and approved senders. A rule has a condition (From, To or Cc, Subject, or any of them; contains, is exactly, ends with) and an action (move to a folder, mark as read, star, Trash, Junk), for one account or all. **Message › Create rule from message…** prefills it with the sender.

Filters apply during sync, client-side, to **new** Inbox messages; existing messages are never moved unless you ask (**Apply now**). Order: an approved sender is never treated as junk; a blocked sender (address or domain `@exemple.fr`) goes to Junk; so does a message flagged as spam by the server’s filter (`X-Spam-Flag`, `X-Spam-Status`…), unless that option is unchecked; otherwise the first matching rule applies. Messages filtered to Junk don’t trigger a notification. **Message › Junk** offers **Report as junk** (Ctrl+Shift+J), **Block sender** and **Not junk** (back to Inbox, sender approved). Rules and lists are stored in the cache (encrypted with it).

**Snooze** (Message › Snooze…, Ctrl+Shift+Z) removes a message from the Inbox until a chosen date (in 3 hours, this evening, tomorrow, Saturday, Monday or a custom date): it is moved to a “Snoozed” folder, created on the server if needed, then returned to its original folder, unread, when the time comes. The message is tracked by its Message-ID, since its IMAP identifier changes with every move. Smail must be open at that time (otherwise the message returns at the next startup); a message manually moved out of “Snoozed” is no longer tracked.

For a newsletter, the reader shows **Unsubscribe** (`List-Unsubscribe` headers). After confirmation, Smail uses, in this order: one-click unsubscribe (RFC 8058: HTTPS request without a browser, cookies or redirects, refused toward a local or private address), an unsubscribe email sent from your account, or opening the page in your browser.

## Offline, sync and comfort

**Settings** controls the light/dark theme, the sync interval (5 minutes initially), the number of messages downloaded automatically per folder (100 initially), IDLE, notifications, minimizing to the notification area, and the interface language (Settings › General: Automatic — follows Windows / Français / English, applied on restart).

Sync runs in a QThread. It walks through the selectable folders, fetches the latest complete messages with their attachments, refreshes flags and reuses content already downloaded. Previously synced content that falls outside this window is removed on the next cycle; messages you opened manually may also be cached. Older messages remain available online, in pages of 50. A page that was never downloaded will not be available offline.

Sync is incremental: only messages missing from the cache are downloaded, and content already present is not rewritten. If the server supports CONDSTORE (RFC 7162, e.g. Gmail, Dovecot, Outlook), a folder whose state hasn’t changed since the last sync (identical STATUS, including HIGHESTMODSEQ) isn’t even opened. Without CONDSTORE, every folder is checked on each cycle.

IMAP IDLE uses a dedicated session per account, compatible with Python 3.11+, to detect Inbox changes. IDLE connections are renewed and reconnect with progressive backoff after a disconnection. If IDLE isn’t supported, periodic sync takes over. Other folders are checked during the periodic cycle. Windows notifications use QSystemTrayIcon and only announce the number of new messages; the first sync does not report old messages.

The **All accounts — Unified inbox** selection gathers the Inboxes already synced and keeps the source account for actions and replies. **Sync** updates all accounts. The **Work offline** checkbox stops new syncs and IDLE sessions, reads from the cache, and blocks new sends/network actions in compose windows. A network operation already in progress may finish before stopping.

If the notification area is available, closing the main window hides it by default. Double-click the icon to reopen it. Its menu offers **Open**, **Sync** and **Quit**. Quit waits for operations to finish and drafts to be saved; connections have bounded timeouts.

## Cache, Windows vault and log

Configuration files are stored in `QStandardPaths.AppLocalDataLocation`, usually `%LOCALAPPDATA%\SmailDesktop\Smail`: `settings.db` and `smail.log`. Passwords are never stored in SQLite. Keyring must use Windows Credential Manager; no fallback to a file or plaintext vault is allowed.

The **Encrypt cached messages, attachments and drafts** option applies Fernet authenticated encryption to content records, with a key stored only in the Windows vault. Migration is transactional, and a VACUUM removes old free pages from the current database. This is application-level content encryption, **not a fully encrypted SQLite file with SQLCipher**: the schema, public account settings and certificate exceptions remain readable. Cache search keys are hashed. The option is off initially; without it, the cache stores content in plaintext on this PC.

Do not delete the `cache-encryption-key` key from the `SmailDesktop` keyring service: without it, an encrypted cache cannot be decrypted. Backing up only `settings.db` does not back up the key. Migration does not encrypt old backups, exports, saved attachment files, or any copies the system may have made earlier.

The SQLite schema is versioned (`PRAGMA user_version`) and migrated automatically at startup; a database created by a newer version of Smail is refused rather than modified. The `cache` table keeps its original structure: a migrated database remains usable by Smail 1.0.0.

Authenticated IMAP sessions are reused for at most 4 minutes (NOOP check before reuse, closed after any error) and message lists are downloaded in one command per page; IDLE keeps its dedicated session.

The log rotates over three 500 KB backups. It contains startup/shutdown, technical error type names and, for an unexpected error, the code files and lines involved; no password, token, mail content or raw server exception is ever written to it. Do not enable detailed tracing in the IMAP/SMTP libraries.

## Code structure

- `core/accounts.py`: public configuration and validation.
- `core/imap_client.py`, `smtp_client.py`: protocols, UID actions, outgoing MIME and IDLE.
- `core/oauth.py`, `tls_policy.py`: OAuth2/PKCE, secrets and certificate policy.
- `core/parser.py`, `html_security.py`: MIME and HTML sanitizing.
- `core/service.py`, `sync.py`: cache, unified inbox, orchestration and Qt threads.
- `storage/database.py`, `secrets.py`: SQLite, content encryption and Windows vault.
- `ui/`: main window, reader, compose, accounts, settings and certificates.
- `utils/`: user folder and rotating log.
- `tests/`: unit tests and local integration tests independent of your accounts.

Network calls, sync and draft saves go through QThreadPool/QThread and Qt signals. Server actions and sends require your clicks in the app; diagnostics and tests use no real account.

## Tests, diagnostics and Windows build

Test and build tools are in `requirements-dev.txt` (which also includes the runtime dependencies):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest mailclient/tests -q
.\.venv\Scripts\python.exe -m mailclient.main --smoke-test
.\.venv\Scripts\python.exe -m PyInstaller --clean Smail.spec
```

The application version is defined once in `mailclient/__init__.py`; `Smail.spec` derives the executable’s version information from it. The `mailclient/ui/assets/smail.ico` icon is generated by `python tools/make_icon.py`. The `.github/workflows/ci.yml` workflow runs the tests on Windows (Python 3.11 and 3.13), builds the executable, runs its diagnostic and publishes the `dist\Smail` folder as an artifact.

The diagnostic briefly opens a window with a dummy message, checks WebEngine and the vault backend, then exits with the expected code 0. It does not load accounts, read their credentials or connect to servers. It may create or migrate the configuration tables and write the usual startup/shutdown events. To test the executable in PowerShell while waiting for its exit code:

```powershell
$p = Start-Process .\dist\Smail\Smail.exe -ArgumentList '--smoke-test' -PassThru -Wait
$p.ExitCode
```

The tests cover MIME, encodings, TLS and fingerprints, STARTTLS without fallback, SQLite, schema and encryption migrations, account removal, bulk actions and folder management, the IMAP session pool, the Windows vault and long tokens, headers/Bcc, replies, drafts, partial sends, no double sending, moving without global purge, literal search, offline cache and the unified inbox. Strictly local servers verify a real SMTP session, the IDLE exchange, the OAuth PKCE/state callback and WebEngine image requests. Headless test rendering uses software mode to avoid GPU issues with the offscreen platform.

Real OAuth authorization must be validated with your own application ID, the provider’s consent and your account. Real sending and actions must be checked with a test account and a controlled recipient. A local suite does not replace these end-to-end checks with your host.

Security references: [Bleach sanitizing](https://bleach.readthedocs.io/en/latest/clean.html), [WebEngine interception](https://doc.qt.io/qt-6.8/qwebengineurlrequestinterceptor.html) and [WebEngine internal scheme](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineUrlSchemeHandler.html).

## Automatic updates and publishing a release

Smail installed by the installer checks the repository’s latest GitHub release every 6 hours (and 45 seconds after startup), using an anonymous request. Three modes, in Settings › General: **Ask me** (default: a banner announces the new version and nothing is downloaded until “Download and install”), **Automatic** (background download without asking) and **Off**. Once downloaded and verified, the update installs silently **when Smail closes**, or right away with “Restart now”. Accounts, cache and settings are kept. Manual check: Tools › Check for updates.

Security: each release contains `smail-update.json` (installer version, name, size and SHA-256) signed with Ed25519 by CI. Smail installs nothing if the signature doesn’t match the embedded public key (`mailclient/core/updater.py`) or if the downloaded file’s hash differs. Only GitHub HTTPS hosts are accepted. After two failed installs of the same version, Smail stops retrying and offers the download page. A copy run from source or from a copied folder only announces the new version.

**Publishing a release:**

1. Describe the changes in the `## Non publié` section of `CHANGELOG.md` and commit.
2. `python tools/release.py 1.2.0 --push`: version number, dated CHANGELOG, commit, `v1.2.0` tag and push.
3. The `.github/workflows/release.yml` workflow tests, builds, signs and publishes the installer. Installed copies of Smail update themselves.

**Signing key (one time only):** the private key is the repository secret `UPDATE_SIGNING_KEY` (full PEM content), added with `gh secret set UPDATE_SIGNING_KEY < chemin\update-signing-key.pem` or under Settings › Secrets and variables › Actions. Keep an offline backup of this file: without it, no update can ever be signed for installed copies. Never put it in the repository.

## Microsoft Store (MSIX package)

`python tools/build_msix.py` turns PyInstaller’s `dist\Smail` folder into a `dist\msix\Smail-X.Y.Z.msix` package, also built by CI for each release (artifact “Smail-msix-vX.Y.Z”, to upload to Partner Center). The package is not signed: the Microsoft Store signs it on publication, which removes the SmartScreen warning. The package identity (`packaging/msix/identity.json`) must match the values in Partner Center › Product management › Product identity. In the Store version, Smail detects its package and leaves updates to the Store. Windows stores a Store copy’s data in the package folder, separately from the installer version.

Local testing without the Store: turn on Windows Developer Mode, then run `python tools/build_msix.py --layout-only` and `Add-AppxPackage -Register dist\msix\layout\AppxManifest.xml` (removal: `Get-AppxPackage *Smail* | Remove-AppxPackage`).

Privacy policy (required by the Store): [PRIVACY.md](PRIVACY.md).

## License

Smail is distributed under the MIT license: see [LICENSE](LICENSE). Lucide icons remain under their own license (`mailclient/ui/assets/LICENSE-LUCIDE.txt`).
