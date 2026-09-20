---
name: ujnotes-local-hosting
description: >-
  Local Windows hosting architecture, Apache Lounge + PHP CGI configuration,
  Caddy reverse proxy, OliveTin Console service, port bindings, and verification commands.
  Use when previewing locally, troubleshooting ujnotes.local, 502 Bad Gateway,
  Caddy TLS, Apache vhosts, or starting the Ujnotes Console.
---

# Local Windows hosting & preview

Ujnotes runs locally as a PHP Cutie site using the native Apache + Caddy architecture on Windows (matching the WCodes pattern, not the Wolo app+site split). Do not add a second Apache instance or listen on port 83.

---

## Architecture & Layout

- **Workspace**: `D:\Ujnotes` (`D:\WCode` is WCode, `D:\Wolo` is Wolo).
- **DocumentRoot**: `D:\Ujnotes\Website\site\project\root` (`interim` and `public` sit beside `root`).
- **Apache**: ApacheLounge 2.4.68 + PHP 8.4.4 CGI at `C:\programs\Apache\httpd`.
  - Windows service: `Apachehttpd` (DisplayName: "Apache httpd", Startup: Automatic). Restarting requires administrative privileges / UAC.
  - PHP configuration: `C:\programs\Apache\httpd\conf\extra\php.conf`.
  - Main configuration: `httpd.conf` includes `IncludeOptional conf/vhosts/*.conf` and `Listen 8084`.
  - Virtual hosts: `C:\programs\Apache\httpd\conf\vhosts\` (local git repository, no GitHub remote).
    - Site configuration file: `ujnotes.conf`.
    - Format requirements: ASCII hyphens, CRLF, UTF-8 no BOM.
    - Leave `wcodes.conf` and `wolo.conf` alone.
  - Plain HTTP only: Apache listens on `:8084` plain HTTP. NameVirtualHost on `:8084`; default server is `wcodes.local`, so `ServerName` must match `ujnotes.local` or requests return WCodes HTML.
- **Caddy (TLS & Reverse Proxy)**:
  - Configuration: `C:\programs\Caddy\caddyfile`.
  - TLS termination: `tls internal` handles local certificates.
  - Proxies:
    - `https://ujnotes.local` $\rightarrow$ `[::1]:8084` (Apache HTTPD).
    - `https://console.ujnotes.local` $\rightarrow$ `127.0.0.1:47821` (OliveTin Console).
  - Reloading: `caddy reload --config C:\programs\Caddy\caddyfile --adapter caddyfile` (usually does not require UAC).
  - First browser visit may prompt to trust Caddy's internal root certificate.
- **Hosts File**:
  - `C:\Windows\System32\drivers\etc\hosts` maps:
    ```
    127.0.0.1 ujnotes.local
    127.0.0.1 console.ujnotes.local
    ```
- **Ujnotes Console**:
  - URL: `https://console.ujnotes.local/`.
  - Engine: OliveTin bound to `127.0.0.1:47821`.
  - Process: Not a Windows service. Auto-start is managed via the current-user scheduled task `Ujnotes Console` (`Register-ConsoleStartup.ps1`).
  - Manual start: Run `D:\Ujnotes\Website\console\Start-Console.ps1` if `https://console.ujnotes.local/` returns 502 Bad Gateway.
- **Docker**:
  - Do not use Docker Desktop, Docker Compose, or `compose-dev.yaml` for day-to-day local preview. Native preview is the primary path.

---

## Verification & Troubleshooting ("Prove it")

Run these checks to confirm local hosting health:

1. **End-to-End HTTPS via Caddy**:
   ```bash
   curl -skI https://ujnotes.local/
   ```
   Must return HTTP 200 with Ujnotes HTML header/title, not WCodes.

2. **Direct Apache Port**:
   ```bash
   curl -sI -H "Host: ujnotes.local" http://127.0.0.1:8084/
   ```
   Confirms Apache is serving `ujnotes.local` without going through Caddy.

3. **502 Bad Gateway Diagnosis**:
   - If `https://ujnotes.local/` returns 502 after an Apache restart, verify Caddy's upstream port. It must be `:8084` (historically `:83` from legacy Docker containers).
   - If `https://console.ujnotes.local/` returns 502, OliveTin is down. Start it via `D:\Ujnotes\Website\console\Start-Console.ps1`.

4. **Console Health**:
   ```bash
   curl -skI https://console.ujnotes.local/
   ```
   Must return HTTP 200 when OliveTin is active.
