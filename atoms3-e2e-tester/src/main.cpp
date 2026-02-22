#include <Arduino.h>

namespace {

constexpr uint32_t kUsbBaud = 115200;
constexpr uint32_t kUnitvBaud = 115200;
constexpr uint16_t kUsbLineMax = 512;
constexpr uint16_t kCamLineMax = 1024;
constexpr uint32_t kDefaultTimeoutMs = 1800;
constexpr uint32_t kDefaultAutoPeriodMs = 1000;

// AtomS3 Lite front Grove connector (PORT.A) is labeled: G / 5V / G2 / G1.
// Field-tested default for this wiring in this repo:
// - Atom RX <- UnitV TX on G1
// - Atom TX -> UnitV RX on G2
// Keep runtime pin override commands because wiring/order is easy to mix up.
constexpr int kDefaultUnitvRxPin = 1;  // G1
constexpr int kDefaultUnitvTxPin = 2;  // G2

HardwareSerial UnitV(1);

enum class LedState {
  Boot,
  Idle,
  Pending,
  LinkOk,
  ScanOk,
  DetectHit,
  Error,
  Timeout,
};

struct PendingRequest {
  bool active = false;
  String reqId;
  String cmd;
  uint32_t sentAtMs = 0;
};

struct Stats {
  uint32_t tx = 0;
  uint32_t rx = 0;
  uint32_t timeouts = 0;
  uint32_t errors = 0;
  uint32_t pingOk = 0;
  uint32_t infoOk = 0;
  uint32_t scanOk = 0;
  uint32_t detectionHits = 0;
  uint32_t lastRttMs = 0;
} g_stats;

struct AutoScanConfig {
  bool enabled = false;
  uint32_t periodMs = kDefaultAutoPeriodMs;
  uint8_t frames = 3;
  bool fastMode = false;
  uint32_t lastSentAtMs = 0;
} g_auto;

PendingRequest g_pending;
uint32_t g_nextReqId = 1;
uint32_t g_timeoutMs = kDefaultTimeoutMs;
int g_unitvRxPin = kDefaultUnitvRxPin;
int g_unitvTxPin = kDefaultUnitvTxPin;

char g_usbLine[kUsbLineMax];
size_t g_usbLen = 0;
char g_camLine[kCamLineMax];
size_t g_camLen = 0;

void setLed(LedState state) {
#ifdef RGB_BUILTIN
  uint8_t r = 0, g = 0, b = 0;
  switch (state) {
    case LedState::Boot: b = 24; break;
    case LedState::Idle: r = 0; g = 0; b = 0; break;
    case LedState::Pending: r = 24; g = 16; b = 0; break;
    case LedState::LinkOk: r = 0; g = 12; b = 18; break;
    case LedState::ScanOk: r = 0; g = 22; b = 0; break;
    case LedState::DetectHit: r = 18; g = 18; b = 18; break;
    case LedState::Error: r = 24; g = 0; b = 0; break;
    case LedState::Timeout: r = 16; g = 8; b = 0; break;
  }
  neopixelWrite(RGB_BUILTIN, r, g, b);
#else
  (void)state;
#endif
}

String trimLine(String s) {
  s.trim();
  return s;
}

bool startsWithWord(const String &line, const char *word) {
  if (!line.startsWith(word)) return false;
  if (line.length() == strlen(word)) return true;
  char c = line.charAt(strlen(word));
  return c == ' ' || c == '\t';
}

String jsonEscape(const String &in) {
  String out;
  out.reserve(in.length() + 8);
  for (size_t i = 0; i < in.length(); ++i) {
    char c = in.charAt(i);
    switch (c) {
      case '\\': out += "\\\\"; break;
      case '"': out += "\\\""; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default: out += c; break;
    }
  }
  return out;
}

String jsonGetString(const String &json, const char *key) {
  String keyPattern = "\"";
  keyPattern += key;
  keyPattern += "\"";
  int p = json.indexOf(keyPattern);
  if (p < 0) return "";
  p += keyPattern.length();
  while (p < json.length() && isspace(static_cast<unsigned char>(json.charAt(p)))) p++;
  if (p >= json.length() || json.charAt(p) != ':') return "";
  p++;
  while (p < json.length() && isspace(static_cast<unsigned char>(json.charAt(p)))) p++;
  if (p >= json.length() || json.charAt(p) != '"') return "";
  int start = p + 1;
  String out;
  out.reserve(16);
  bool esc = false;
  for (int i = start; i < json.length(); ++i) {
    char c = json.charAt(i);
    if (esc) {
      out += c;
      esc = false;
      continue;
    }
    if (c == '\\') {
      esc = true;
      continue;
    }
    if (c == '"') {
      return out;
    }
    out += c;
  }
  return "";
}

bool jsonContainsOkTrue(const String &json) {
  int p = json.indexOf("\"ok\"");
  if (p < 0) return false;
  p = json.indexOf(':', p);
  if (p < 0) return false;
  p++;
  while (p < json.length() && isspace(static_cast<unsigned char>(json.charAt(p)))) p++;
  return json.startsWith("true", p);
}

bool jsonContainsError(const String &json) {
  return json.indexOf("\"error\"") >= 0;
}

bool jsonObjectsNonEmpty(const String &json) {
  int p = json.indexOf("\"objects\"");
  if (p < 0) return false;
  p = json.indexOf(':', p);
  if (p < 0) return false;
  p = json.indexOf('[', p);
  if (p < 0) return false;
  for (int i = p + 1; i < json.length(); ++i) {
    char c = json.charAt(i);
    if (c == ' ' || c == '\t' || c == '\r' || c == '\n') continue;
    return c != ']';
  }
  return false;
}

bool responseIndicatesDetectionHit(const String &json) {
  String person = jsonGetString(json, "person");
  if (person.length() > 0 && person != "NONE") {
    return true;
  }
  return jsonObjectsNonEmpty(json);
}

void printBanner();
void printHelp();
void printStats();
void beginUnitvUart(int rxPin, int txPin);
bool sendRawJsonLine(const String &line, const String &tag);
bool sendCommandJson(const String &cmd, const String &argsJson = "{}");
void handleUsbCommand(String line);
void handleCamLine(const char *line);

void logLine(const char *prefix, const String &line) {
  Serial.printf("[%10lu] %s %s\n", millis(), prefix, line.c_str());
}

void clearPending(const char *reason = nullptr) {
  if (reason && g_pending.active) {
    Serial.printf("[%10lu] pending cleared (%s): req_id=%s cmd=%s\n",
                  millis(), reason, g_pending.reqId.c_str(), g_pending.cmd.c_str());
  }
  g_pending = PendingRequest{};
}

bool sendRawJsonLine(const String &line, const String &tag) {
  if (g_pending.active) {
    Serial.println("BUSY: waiting response from camera, retry after response/timeout");
    return false;
  }

  String reqId = jsonGetString(line, "req_id");
  String cmd = jsonGetString(line, "cmd");
  if (reqId.isEmpty()) {
    reqId = String(g_nextReqId++);
    String patched = line;
    int brace = patched.indexOf('{');
    if (brace >= 0) {
      patched.remove(brace, 1);
      patched = "{\"req_id\":\"" + reqId + "\"," + patched;
    }
    if (patched.length() == 0 || patched.charAt(patched.length() - 1) != '}') {
      Serial.println("RAW JSON must be a single JSON object");
      return false;
    }
    return sendRawJsonLine(patched, tag);
  }

  if (cmd.isEmpty()) {
    cmd = "RAW";
  }

  UnitV.print(line);
  UnitV.print('\n');
  g_pending.active = true;
  g_pending.reqId = reqId;
  g_pending.cmd = cmd;
  g_pending.sentAtMs = millis();
  g_stats.tx++;
  setLed(LedState::Pending);

  logLine("TX->UNITV", line);
  return true;
}

bool sendCommandJson(const String &cmd, const String &argsJson) {
  String reqId = String(g_nextReqId++);
  String json = "{\"cmd\":\"";
  json += jsonEscape(cmd);
  json += "\",\"req_id\":\"";
  json += reqId;
  json += "\"";
  if (argsJson.length() > 0) {
    json += ",\"args\":";
    json += argsJson;
  }
  json += "}";
  return sendRawJsonLine(json, cmd);
}

void sendPing() { (void)sendCommandJson("PING", "{}"); }
void sendInfo() { (void)sendCommandJson("INFO", "{}"); }
void sendWho(uint8_t frames, bool fast) {
  String args = String("{\"mode\":\"") + (fast ? "FAST" : "RELIABLE") +
                "\",\"frames\":" + String(frames) + "}";
  (void)sendCommandJson("WHO", args);
}
void sendObjects(uint8_t frames, bool fast) {
  String args = String("{\"mode\":\"") + (fast ? "FAST" : "RELIABLE") +
                "\",\"frames\":" + String(frames) + "}";
  (void)sendCommandJson("OBJECTS", args);
}
void sendScan(uint8_t frames, bool fast) {
  String args = String("{\"mode\":\"") + (fast ? "FAST" : "RELIABLE") +
                "\",\"frames\":" + String(frames) + "}";
  (void)sendCommandJson("SCAN", args);
}

void printBanner() {
  Serial.println();
  Serial.println("AtomS3 Lite <-> UnitV E2E tester");
  Serial.printf("USB Serial: %lu, UnitV UART: %lu (TX=%d RX=%d)\n",
                static_cast<unsigned long>(kUsbBaud),
                static_cast<unsigned long>(kUnitvBaud),
                g_unitvTxPin, g_unitvRxPin);
  Serial.println("Type 'help' for commands. First quick check: ping");
}

void printHelp() {
  Serial.println("Commands:");
  Serial.println("  help");
  Serial.println("  ping");
  Serial.println("  info");
  Serial.println("  scan [frames] [fast|reliable]");
  Serial.println("  who [frames] [fast|reliable]");
  Serial.println("  objects [frames] [fast|reliable]");
  Serial.println("  auto on [period_ms] [frames] [fast|reliable]");
  Serial.println("  auto off");
  Serial.println("  timeout <ms>");
  Serial.println("  pins                       (show UART pins)");
  Serial.println("  pinswap                    (swap current RX/TX pins)");
  Serial.println("  uartpins <rx> <tx>         (reinit UART on custom pins)");
  Serial.println("  stats");
  Serial.println("  clear");
  Serial.println("  raw {\"cmd\":\"PING\",\"req_id\":\"123\"}");
  Serial.println("  Any line starting with '{' is treated as raw JSON and sent to UnitV");
}

void printStats() {
  Serial.printf(
      "stats tx=%lu rx=%lu timeouts=%lu errors=%lu ping_ok=%lu info_ok=%lu scan_ok=%lu "
      "detect_hits=%lu last_rtt_ms=%lu pending=%s auto=%s\n",
      static_cast<unsigned long>(g_stats.tx),
      static_cast<unsigned long>(g_stats.rx),
      static_cast<unsigned long>(g_stats.timeouts),
      static_cast<unsigned long>(g_stats.errors),
      static_cast<unsigned long>(g_stats.pingOk),
      static_cast<unsigned long>(g_stats.infoOk),
      static_cast<unsigned long>(g_stats.scanOk),
      static_cast<unsigned long>(g_stats.detectionHits),
      static_cast<unsigned long>(g_stats.lastRttMs),
      g_pending.active ? "yes" : "no",
      g_auto.enabled ? "on" : "off");
}

void beginUnitvUart(int rxPin, int txPin) {
  g_unitvRxPin = rxPin;
  g_unitvTxPin = txPin;
  UnitV.end();
  delay(10);
  UnitV.begin(kUnitvBaud, SERIAL_8N1, g_unitvRxPin, g_unitvTxPin);
  Serial.printf("UnitV UART reinit: RX=%d TX=%d @ %lu\n",
                g_unitvRxPin, g_unitvTxPin,
                static_cast<unsigned long>(kUnitvBaud));
}

uint8_t parseFramesOrDefault(const String &token, uint8_t defVal) {
  if (token.isEmpty()) return defVal;
  long v = token.toInt();
  if (v <= 0) return defVal;
  if (v > 5) v = 5;
  return static_cast<uint8_t>(v);
}

bool parseFastToken(const String &token, bool defVal) {
  if (token.isEmpty()) return defVal;
  String t = token;
  t.toLowerCase();
  if (t == "fast") return true;
  if (t == "reliable") return false;
  return defVal;
}

String tokenAt(const String &line, uint8_t index) {
  uint8_t current = 0;
  int i = 0;
  while (i < line.length()) {
    while (i < line.length() && isspace(static_cast<unsigned char>(line[i]))) i++;
    if (i >= line.length()) break;
    int start = i;
    while (i < line.length() && !isspace(static_cast<unsigned char>(line[i]))) i++;
    if (current == index) return line.substring(start, i);
    current++;
  }
  return "";
}

void handleUsbCommand(String line) {
  line = trimLine(line);
  if (line.isEmpty()) return;

  if (line.startsWith("{")) {
    (void)sendRawJsonLine(line, "RAW");
    return;
  }
  if (startsWithWord(line, "raw")) {
    String payload = trimLine(line.substring(3));
    if (!payload.startsWith("{")) {
      Serial.println("raw expects a JSON object");
      return;
    }
    (void)sendRawJsonLine(payload, "RAW");
    return;
  }

  String cmd = tokenAt(line, 0);
  cmd.toLowerCase();

  if (cmd == "help" || cmd == "?") {
    printHelp();
    return;
  }
  if (cmd == "ping") {
    sendPing();
    return;
  }
  if (cmd == "info") {
    sendInfo();
    return;
  }
  if (cmd == "scan" || cmd == "who" || cmd == "objects") {
    const uint8_t frames = parseFramesOrDefault(tokenAt(line, 1), 3);
    const bool fast = parseFastToken(tokenAt(line, 2), false);
    if (cmd == "scan") sendScan(frames, fast);
    if (cmd == "who") sendWho(frames, fast);
    if (cmd == "objects") sendObjects(frames, fast);
    return;
  }
  if (cmd == "auto") {
    String sub = tokenAt(line, 1);
    sub.toLowerCase();
    if (sub == "off") {
      g_auto.enabled = false;
      Serial.println("auto scan disabled");
      return;
    }
    if (sub == "on") {
      long period = tokenAt(line, 2).toInt();
      if (period <= 0) period = kDefaultAutoPeriodMs;
      if (period < 200) period = 200;
      g_auto.periodMs = static_cast<uint32_t>(period);
      g_auto.frames = parseFramesOrDefault(tokenAt(line, 3), 3);
      g_auto.fastMode = parseFastToken(tokenAt(line, 4), false);
      g_auto.enabled = true;
      g_auto.lastSentAtMs = 0;
      Serial.printf("auto scan enabled: period=%lu ms frames=%u mode=%s\n",
                    static_cast<unsigned long>(g_auto.periodMs),
                    g_auto.frames,
                    g_auto.fastMode ? "FAST" : "RELIABLE");
      return;
    }
    Serial.println("usage: auto on [period_ms] [frames] [fast|reliable] | auto off");
    return;
  }
  if (cmd == "timeout") {
    long t = tokenAt(line, 1).toInt();
    if (t < 200) {
      Serial.println("timeout must be >= 200 ms");
      return;
    }
    g_timeoutMs = static_cast<uint32_t>(t);
    Serial.printf("timeout=%lu ms\n", static_cast<unsigned long>(g_timeoutMs));
    return;
  }
  if (cmd == "pins") {
    Serial.printf("UnitV UART pins: RX=%d TX=%d\n", g_unitvRxPin, g_unitvTxPin);
    return;
  }
  if (cmd == "pinswap") {
    if (g_pending.active) {
      Serial.println("Cannot swap pins while request is pending");
      return;
    }
    beginUnitvUart(g_unitvTxPin, g_unitvRxPin);
    return;
  }
  if (cmd == "uartpins") {
    long rx = tokenAt(line, 1).toInt();
    long tx = tokenAt(line, 2).toInt();
    if (rx < 0 || tx < 0) {
      Serial.println("usage: uartpins <rx> <tx>");
      return;
    }
    if (g_pending.active) {
      Serial.println("Cannot reinit UART while request is pending");
      return;
    }
    beginUnitvUart(static_cast<int>(rx), static_cast<int>(tx));
    return;
  }
  if (cmd == "stats") {
    printStats();
    return;
  }
  if (cmd == "clear") {
    g_stats = Stats{};
    Serial.println("stats cleared");
    return;
  }

  Serial.println("Unknown command. Type 'help'.");
}

void handleCamLine(const char *line) {
  String s(line);
  g_stats.rx++;
  logLine("RX<-UNITV", s);

  const bool ok = jsonContainsOkTrue(s);
  const bool hasErr = jsonContainsError(s);
  const String respReqId = jsonGetString(s, "req_id");

  if (g_pending.active && respReqId == g_pending.reqId) {
    g_stats.lastRttMs = millis() - g_pending.sentAtMs;

    if (ok) {
      String cmd = g_pending.cmd;
      cmd.toUpperCase();
      if (cmd == "PING") g_stats.pingOk++;
      if (cmd == "INFO") g_stats.infoOk++;
      if (cmd == "SCAN") g_stats.scanOk++;

      if (responseIndicatesDetectionHit(s)) {
        g_stats.detectionHits++;
        setLed(LedState::DetectHit);
        Serial.printf("[%10lu] E2E HIT: camera produced non-empty recognition result\n", millis());
      } else if (cmd == "PING" || cmd == "INFO") {
        setLed(LedState::LinkOk);
      } else {
        setLed(LedState::ScanOk);
      }
    } else {
      if (hasErr) {
        g_stats.errors++;
      }
      setLed(LedState::Error);
    }

    clearPending();
  } else {
    // Unexpected/unsolicited line (shouldn't happen for current firmware, but show it).
    if (ok) {
      setLed(LedState::ScanOk);
    } else if (hasErr) {
      setLed(LedState::Error);
    }
  }
}

void pollUsbConsole() {
  while (Serial.available() > 0) {
    const int c = Serial.read();
    if (c < 0) return;
    if (c == '\r') continue;
    if (c == '\n') {
      g_usbLine[g_usbLen] = '\0';
      handleUsbCommand(String(g_usbLine));
      g_usbLen = 0;
      continue;
    }
    if (g_usbLen + 1 >= kUsbLineMax) {
      g_usbLen = 0;
      Serial.println("USB line too long; buffer cleared");
      continue;
    }
    g_usbLine[g_usbLen++] = static_cast<char>(c);
  }
}

void pollUnitvUart() {
  while (UnitV.available() > 0) {
    const int c = UnitV.read();
    if (c < 0) return;
    if (c == '\r') continue;
    if (c == '\n') {
      g_camLine[g_camLen] = '\0';
      if (g_camLen > 0) {
        handleCamLine(g_camLine);
      }
      g_camLen = 0;
      continue;
    }
    if (g_camLen + 1 >= kCamLineMax) {
      g_camLen = 0;
      g_stats.errors++;
      setLed(LedState::Error);
      Serial.println("Camera UART line too long; buffer cleared");
      continue;
    }
    g_camLine[g_camLen++] = static_cast<char>(c);
  }
}

void servicePendingTimeout() {
  if (!g_pending.active) return;
  if (millis() - g_pending.sentAtMs <= g_timeoutMs) return;

  g_stats.timeouts++;
  Serial.printf("[%10lu] TIMEOUT waiting response: req_id=%s cmd=%s (>%lu ms)\n",
                millis(), g_pending.reqId.c_str(), g_pending.cmd.c_str(),
                static_cast<unsigned long>(g_timeoutMs));
  setLed(LedState::Timeout);
  clearPending("timeout");
}

void serviceAutoScan() {
  if (!g_auto.enabled || g_pending.active) return;
  const uint32_t now = millis();
  if (g_auto.lastSentAtMs != 0 && (now - g_auto.lastSentAtMs) < g_auto.periodMs) return;
  g_auto.lastSentAtMs = now;
  sendScan(g_auto.frames, g_auto.fastMode);
}

}  // namespace

void setup() {
  setLed(LedState::Boot);

  Serial.begin(kUsbBaud);
  const uint32_t waitStart = millis();
  while (!Serial && millis() - waitStart < 2500) {
    delay(10);
  }

  beginUnitvUart(g_unitvRxPin, g_unitvTxPin);

  delay(80);
  printBanner();
  printHelp();
  setLed(LedState::Idle);
}

void loop() {
  pollUsbConsole();
  pollUnitvUart();
  servicePendingTimeout();
  serviceAutoScan();
  delay(1);
}
void beginUnitvUart(int rxPin, int txPin) {
  g_unitvRxPin = rxPin;
  g_unitvTxPin = txPin;
  UnitV.end();
  delay(10);
  UnitV.begin(kUnitvBaud, SERIAL_8N1, g_unitvRxPin, g_unitvTxPin);
  Serial.printf("UnitV UART reinit: RX=%d TX=%d @ %lu\n",
                g_unitvRxPin, g_unitvTxPin,
                static_cast<unsigned long>(kUnitvBaud));
}
