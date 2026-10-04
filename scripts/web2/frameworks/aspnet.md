# ASP.NET — fingerprint→CVE reflex

> Identified ASP.NET (Webforms/WCF/SharePoint) → reflex: ViewState-differential + trace/elmah + Telerik +
> SharePoint. White-hat: read-only. Deserialize-RCE (ViewState/Telerik) is described as class + detection;
> do NOT build a machineKey forge or a ysoserial chain — prove the primitive + reachability.

## Fingerprint

- **Headers:** `X-AspNet-Version: 4.0.30319` (classic .NET Framework; .NET Core/5+ does NOT emit it),
  `X-AspNetMvc-Version`, `X-Powered-By: ASP.NET`, `Server: Microsoft-IIS/…`.
- **Cookies:** `ASP.NET_SessionId`, `.ASPXAUTH`/`.ASPXFORMSAUTH` (Forms-auth), `FedAuth` (WS-Federation).
- **Body:** `<input … name="__VIEWSTATE">`, `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION`,
  `__REQUESTDIGEST` (SharePoint CSRF), `__VIEWSTATEENCRYPTED` (empty = signed-only).
- **Paths:** `*.aspx`/`*.asmx`/`*.svc`, `/trace.axd`, `/elmah.axd`, `/Telerik.Web.UI.WebResource.axd`,
  `/_layouts/` (SharePoint).
- **Version:** a stale-ViewState POST → 500 with `Version Information: Microsoft .NET Framework Version:…`.

## Known-CVE reflexes

- **ViewState deserialization (the class — headline RCE, gated on machineKey).**
  - Class: `__VIEWSTATEENCRYPTED=""` (or absent) = signed-only. Recovering the `validationKey`
    (from a web.config leak / elmah / source / GitHub) → forge ViewState → `TypeConfuseDelegate`-class RCE in
    `w3wp.exe`.
  - Check: grep forms for `name="__VIEWSTATE"`; is `__VIEWSTATEENCRYPTED` empty? → signed-only primitive.
    Do NOT perform the machineKey forge.
  - Detection Signal: signed-only ViewState = a Low-Medium primitive; Critical ONLY with a recovered
    machineKey (prove the key exists as a separate finding).

- **Dual-parser MAC-bypass anti-pattern (the class).**
  - Class: `ObjectStateFormatter` (legacy) parses SOME shapes BEFORE the `LosFormatter` MAC check →
    a MAC-before-parse bypass.
  - Check (7-shape differential, non-destructive): a trivial `AAAA` → `"Validation of viewstate MAC failed"`;
    an XML-shaped `<xss/>` and a LosFormatter prefix → `"The state information is invalid for this page…"` (a
    DIFFERENT parser path).
  - Detection Signal: a divergence in error messages between shapes = two entry points, one before the MAC.

- **`/trace.axd` · `/elmah.axd` disclosure (the class).**
  - Class: `trace.axd` → a dump of the last requests with headers/form-data (Authorization/session cookies);
    `elmah.axd` → an error log with stack traces and sometimes a connection string.
  - Check: `curl -o /dev/null -w "%{http_code}" "/trace.axd"` / `/elmah.axd` → 200 anonymously?
    403 localhost-only → try `X-Forwarded-For: 127.0.0.1`.
  - Detection Signal: 200 with LIVE `Authorization: Bearer`/session/connection-string = Critical. Clean stack
    traces without creds = Low.

- **Telerik UI RadAsyncUpload RCE — CVE-2017-11317** (packing key in the public DLL before 2017.1.118),
  **CVE-2019-18935** (deserialize via `dialogParametersHolder`, needs the encryption key), CVE-2017-11357.
  - Class: `Telerik.Web.UI.WebResource.axd?type=rau` → upload-to-RCE (CVE-2017-11317) / insecure-deserialize
    (CVE-2019-18935).
  - Check: `curl -X POST "/Telerik.Web.UI.WebResource.axd?type=rau"` → a RadAsyncUploadHandler response? Take
    the version from the SERVER (`WebResource.axd` headers), NOT from the JS bundle (the client DLL != the
    server DLL).
  - Detection Signal: the RAU handler responds + the server version is in the vulnerable range = RCE precondition.

- **SharePoint ToolShell — CVE-2025-53770** (+ CVE-2025-53771; on-prem SharePoint 2016/2019/SE).
  - Class: `ToolPane.aspx?DisplayMode=Edit` anonymously + an anonymous `__REQUESTDIGEST` (`_api/contextinfo`)
    + signed-only ViewState → unauth deserialize-RCE.
  - Check: `curl "/_layouts/15/ToolPane.aspx?DisplayMode=Edit"` → 200 anonymously? `__VIEWSTATEENCRYPTED`
    empty? is a digest issued anonymously?
  - Detection Signal: a reachable ToolPane + an anonymous digest + signed-only VS = the ToolShell precondition
    chain (Critical). Full RCE — see `hunt-sharepoint`; do not run the exploit chain.

- **`customErrors mode="Off"` (info disclosure).**
  - Class: a 500 returns a full stack trace — methods/paths/version banner anonymously.
  - Check: trigger a parser-level error (a malformed Content-Length / oversize ViewState) → a stack trace?
  - Detection Signal: a stack trace with internal paths = Low (High only with creds/connection-string).

- **WCF `.svc` / `.asmx` forgotten endpoints (the class).**
  - Class: `.svc?wsdl`/`?mex` — metadata (admin operations) is often anonymously enumerable even when the
    operations themselves 401.
  - Check: grep the body for `\.svc`; `curl "/Service.svc?wsdl"`, `?mex`.
  - Detection Signal: a WSDL/MEX with admin contracts anonymously = surface (auth-drift on the operations).
