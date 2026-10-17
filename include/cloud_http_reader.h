#ifndef CLOUD_HTTP_READER_H
#define CLOUD_HTTP_READER_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// Small HTTP/1 response reader for the cloud account endpoint. Stream's timed
// helpers differ between Arduino core versions and treat temporary TLS silence
// as a partial line/EOF. Read only available bytes, yield during gaps, and apply
// one absolute deadline to the entire response, including chunk trailers.
namespace cloud_http {
enum class Result { Complete, Timeout, Disconnected, Malformed, TooLarge, OutOfMemory };
constexpr size_t kLineLimit = 2048;
constexpr size_t kHeaderLimit = 12288;
constexpr size_t kCookieLimit = 4096;

inline bool equalIgnoreCase(const char* a, const char* b) {
  while (*a && *b) {
    const char x = *a >= 'A' && *a <= 'Z' ? *a + ('a' - 'A') : *a;
    const char y = *b >= 'A' && *b <= 'Z' ? *b + ('a' - 'A') : *b;
    if (x != y) return false;
    ++a; ++b;
  }
  return *a == *b;
}
inline char* trim(char* s) {
  while (*s == ' ' || *s == '\t') ++s;
  size_t n = strlen(s);
  while (n && (s[n-1] == ' ' || s[n-1] == '\t')) s[--n] = 0;
  return s;
}
inline bool number(const char* s, unsigned base, size_t& out, bool extension = false) {
  out = 0;
  bool digit = false;
  while (*s) {
    if (extension && *s == ';') return digit;
    unsigned value = *s >= '0' && *s <= '9' ? unsigned(*s - '0') :
      *s >= 'a' && *s <= 'f' ? unsigned(*s - 'a' + 10) :
      *s >= 'A' && *s <= 'F' ? unsigned(*s - 'A' + 10) : 255;
    if (value >= base || out > (SIZE_MAX - value) / base) return false;
    out = out * base + value;
    digit = true;
    ++s;
  }
  return digit;
}

template<class Stream, class Clock, class Wait>
class Reader {
 public:
  Reader(Stream& stream, Clock& clock, Wait& wait, uint32_t limit)
    : stream_(stream), clock_(clock), wait_(wait), started_(clock()), limit_(limit) {}
  Result byte(char& out) {
    while (uint32_t(clock_() - started_) < limit_) {
      if (stream_.available() > 0) {
        uint8_t value;
        if (stream_.read(&value, 1) == 1) { out = char(value); return Result::Complete; }
      } else if (!stream_.connected()) return Result::Disconnected;
      wait_();
    }
    return Result::Timeout;
  }
  Result line(char* buffer, size_t size, size_t* budget = nullptr) {
    size_t n = 0;
    bool cr = false;
    while (true) {
      char c;
      const auto r = byte(c);
      if (r != Result::Complete) return r;
      if (budget && ++*budget > kHeaderLimit) return Result::TooLarge;
      if (cr) {
        if (c != '\n') return Result::Malformed;
        buffer[n] = 0;
        return Result::Complete;
      }
      if (c == '\r') { cr = true; continue; }
      if (c == '\n' || c == 0) return Result::Malformed;
      if (n + 1 >= size) return Result::TooLarge;
      buffer[n++] = c;
    }
  }
  template<class Text>
  Result body(Text& output, size_t count, size_t cap) {
    if (output.length() > cap || count > cap - output.length()) return Result::TooLarge;
    char buffer[129];
    while (count) {
      const size_t n = count < sizeof(buffer)-1 ? count : sizeof(buffer)-1;
      for (size_t i = 0; i < n; ++i) {
        const auto r = byte(buffer[i]);
        if (r != Result::Complete) return r;
        if (buffer[i] == 0) return Result::Malformed; // JSON/cookies are text
      }
      buffer[n] = 0;
      const size_t before = output.length();
      output += buffer;
      if (output.length() != before + n) return Result::OutOfMemory;
      count -= n;
    }
    return Result::Complete;
  }
 private:
  Stream& stream_;
  Clock& clock_;
  Wait& wait_;
  const uint32_t started_;
  const uint32_t limit_;
};

template<class Stream, class Text, class Clock, class Wait>
Result readResponse(Stream& stream, int& status, Text& cookies, Text& body,
                    size_t maxBody, Clock clock, Wait wait, uint32_t timeoutMs = 12000) {
  Reader<Stream, Clock, Wait> reader(stream, clock, wait, timeoutMs);
  char line[kLineLimit];
  size_t headerBytes = 0;
  auto r = reader.line(line, sizeof line, &headerBytes);
  if (r != Result::Complete) return r;
  if (strlen(line) < 12 || (strncmp(line, "HTTP/1.1 ", 9) && strncmp(line, "HTTP/1.0 ", 9)) ||
      line[9] < '2' || line[9] > '5' || line[10] < '0' || line[10] > '9' ||
      line[11] < '0' || line[11] > '9' || (line[12] && line[12] != ' ')) return Result::Malformed;
  status = (line[9]-'0')*100 + (line[10]-'0')*10 + line[11]-'0';
  size_t contentLength = 0;
  bool haveLength = false, chunked = false;
  while (true) {
    r = reader.line(line, sizeof line, &headerBytes);
    if (r != Result::Complete) return r;
    if (!*line) break;
    char* colon = strchr(line, ':');
    if (!colon || colon == line) return Result::Malformed;
    *colon = 0;
    char* value = trim(colon+1);
    if (equalIgnoreCase(line, "content-length")) {
      size_t n;
      if (!number(value, 10, n) || (haveLength && n != contentLength)) return Result::Malformed;
      contentLength = n;
      haveLength = true;
    } else if (equalIgnoreCase(line, "transfer-encoding")) {
      if (chunked || !equalIgnoreCase(value, "chunked")) return Result::Malformed;
      chunked = true;
    } else if (equalIgnoreCase(line, "set-cookie")) {
      const size_t n = strlen(value);
      if (cookies.length() > kCookieLimit || n + 1 > kCookieLimit - cookies.length()) return Result::TooLarge;
      const size_t before = cookies.length();
      cookies += value;
      cookies += '\n';
      if (cookies.length() != before + n + 1) return Result::OutOfMemory;
    }
  }
  if (chunked && haveLength) return Result::Malformed;
  if (status == 204 || status == 304) return Result::Complete;
  if (chunked) {
    while (true) {
      r = reader.line(line, sizeof line);
      if (r != Result::Complete) return r;
      size_t count;
      if (!number(line, 16, count, true)) return Result::Malformed;
      if (!count) {
        // Trailers are bounded too; never accept an incomplete final chunk.
        do {
          r = reader.line(line, sizeof line, &headerBytes);
          if (r != Result::Complete) return r;
          if (*line && !strchr(line, ':')) return Result::Malformed;
        } while (*line);
        return Result::Complete;
      }
      r = reader.body(body, count, maxBody);
      if (r != Result::Complete) return r;
      r = reader.line(line, sizeof line);
      if (r != Result::Complete) return r;
      if (*line) return Result::Malformed;
    }
  }
  if (haveLength) return reader.body(body, contentLength, maxBody);
  // HTTP/1 close-delimited body. TLS EOF is only completion in this mode.
  while (true) {
    char c;
    r = reader.byte(c);
    if (r == Result::Disconnected) return Result::Complete;
    if (r != Result::Complete) return r;
    if (c == 0) return Result::Malformed;
    if (body.length() >= maxBody) return Result::TooLarge;
    const size_t before = body.length();
    body += c;
    if (body.length() != before + 1) return Result::OutOfMemory;
  }
}
} // namespace cloud_http
#endif
