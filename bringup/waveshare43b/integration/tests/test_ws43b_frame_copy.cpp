#include "ws43b_frame_copy.h"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <vector>

// Native checks for the exact production copy/release helper. They cannot
// establish PSRAM, ISR timing, RGB scanout, or physical-screen correctness.
namespace {
size_t checks = 0;
void expect(bool condition, const char *message) {
  ++checks;
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    std::exit(1);
  }
}

struct GuardedWords {
  static constexpr size_t guardWords = 16;
  static constexpr uint32_t guard = 0xb16bcafe;
  std::vector<uint32_t> storage;
  size_t words;

  explicit GuardedWords(size_t count)
      : storage(count + 2 * guardWords, guard), words(count) {}
  uint32_t *data() { return storage.data() + guardWords; }
  const uint32_t *data() const { return storage.data() + guardWords; }
  uint8_t *bytes() { return reinterpret_cast<uint8_t *>(data()); }
  const uint8_t *bytes() const { return reinterpret_cast<const uint8_t *>(data()); }
  size_t byteSize() const { return words * sizeof(uint32_t); }
  bool guardsIntact() const {
    return std::all_of(storage.begin(), storage.begin() + guardWords,
                       [](uint32_t value) { return value == guard; }) &&
           std::all_of(storage.end() - guardWords, storage.end(),
                       [](uint32_t value) { return value == guard; });
  }
};

uint32_t pattern(size_t index, size_t rowWords, unsigned frame) {
  switch (frame % 5) {
  case 0: return 0;
  case 1: return UINT32_MAX;
  case 2: return index & 1 ? 0x07e0f800u : 0xffff001fu; // RGB565 pairs
  case 3: return (uint32_t(index / rowWords) << 20) ^ uint32_t(index % rowWords);
  default: {
    uint32_t value = uint32_t(index) + 0x9e3779b9u * (frame + 1);
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    return value;
  }
  }
}

void exerciseGeometry(size_t rowBytes, size_t rows) {
  const size_t words = rowBytes * rows / sizeof(uint32_t);
  GuardedWords source(words), first(words), second(words);
  // Extra scratch space must remain untouched beyond the requested row.
  GuardedWords scratch(rowBytes / sizeof(uint32_t) + 9);
  for (unsigned frame = 0; frame < 12; ++frame) {
    for (size_t i = 0; i < words; ++i)
      source.data()[i] = pattern(i, rowBytes / sizeof(uint32_t), frame);
    GuardedWords &destination = frame & 1 ? first : second;
    const GuardedWords &untouched = frame & 1 ? second : first;
    const auto beforeSource = source.storage;
    const auto beforeUntouched = untouched.storage;
    expect(ws43b::copyFrameChecked(destination.bytes(), source.bytes(),
                                  scratch.data(), scratch.byteSize(), rowBytes, rows),
           "copy an entire frame through row scratch");
    expect(std::equal(source.data(), source.data() + words, destination.data()),
           "destination matches every source word, including final row");
    expect(source.storage == beforeSource, "copy leaves source and its guards unchanged");
    expect(untouched.storage == beforeUntouched, "copy leaves the other scanout buffer unchanged");
    expect(destination.guardsIntact() && scratch.guardsIntact(),
           "copy leaves destination and scratch guards unchanged");
    expect(std::all_of(scratch.data() + rowBytes / sizeof(uint32_t),
                       scratch.data() + scratch.words,
                       [](uint32_t value) { return value == GuardedWords::guard; }),
           "copy does not write beyond a row in larger scratch");
  }
}

void invalidArguments() {
  constexpr size_t rowBytes = 512, rows = 3;
  GuardedWords source(rowBytes * rows / 4), destination(rowBytes * rows / 4);
  GuardedWords scratch(rowBytes / 4);
  for (size_t i = 0; i < source.words; ++i) source.data()[i] = uint32_t(i) ^ 0xa5a51234u;
  const auto sourceBefore = source.storage;
  const auto destinationBefore = destination.storage;
  const auto scratchBefore = scratch.storage;
  auto reject = [&](uint8_t *dst, const uint8_t *src, uint32_t *tmp,
                    size_t tmpBytes, size_t widthBytes, size_t height,
                    const char *message) {
    expect(!ws43b::copyFrameChecked(dst, src, tmp, tmpBytes, widthBytes, height), message);
    expect(source.storage == sourceBefore && destination.storage == destinationBefore &&
               scratch.storage == scratchBefore,
           "invalid arguments cause no writes to any supplied allocation");
  };
  auto *dst = destination.bytes();
  const auto *src = source.bytes();
  auto *tmp = scratch.data();
  reject(nullptr, src, tmp, rowBytes, rowBytes, rows, "reject null destination");
  reject(dst, nullptr, tmp, rowBytes, rowBytes, rows, "reject null source");
  reject(dst, src, nullptr, rowBytes, rowBytes, rows, "reject null scratch");
  reject(dst, src, tmp, rowBytes, 0, rows, "reject zero row size");
  reject(dst, src, tmp, rowBytes, rowBytes, 0, "reject zero rows");
  reject(dst, src, tmp, 0, rowBytes, rows, "reject zero scratch size");
  reject(dst, src, tmp, rowBytes - 1, rowBytes, rows, "reject short scratch");
  reject(dst, src, tmp, rowBytes, rowBytes - 1, rows, "reject partial 32-bit word in row");
  reject(dst + 1, src, tmp, rowBytes, rowBytes, rows, "reject unaligned destination");
  reject(dst, src + 1, tmp, rowBytes, rowBytes, rows, "reject unaligned source");
  reject(dst, src, reinterpret_cast<uint32_t *>(scratch.bytes() + 1),
         rowBytes, rowBytes, rows, "reject unaligned scratch");
  reject(dst, src, tmp, rowBytes, rowBytes, SIZE_MAX / rowBytes + 1,
         "reject frame size multiplication overflow");
  const uintptr_t highAddress = UINTPTR_MAX & ~uintptr_t(3);
  reject(reinterpret_cast<uint8_t *>(highAddress), src, tmp, rowBytes, rowBytes, rows,
         "reject destination end-address overflow before dereference");
  reject(dst, reinterpret_cast<const uint8_t *>(highAddress), tmp, rowBytes, rowBytes, rows,
         "reject source end-address overflow before dereference");
  reject(dst, src, reinterpret_cast<uint32_t *>(highAddress), rowBytes, rowBytes, rows,
         "reject scratch end-address overflow before dereference");
  reject(source.bytes(), src, tmp, rowBytes, rowBytes, rows, "reject identical source and destination");
  reject(source.bytes() + 4, src, tmp, rowBytes, rowBytes, rows, "reject forward frame overlap");
  reject(source.bytes(), src + 4, tmp, rowBytes, rowBytes, rows, "reject backward frame overlap");
  reject(dst, src, source.data(), rowBytes, rowBytes, rows, "reject scratch inside source");
  reject(dst, src, destination.data(), rowBytes, rowBytes, rows, "reject scratch inside destination");
  reject(dst, src, source.data() + source.words - rowBytes / 4,
         rowBytes, rowBytes, rows, "reject scratch overlapping the final source row");
}

void adjacentRanges() {
  constexpr size_t rowBytes = 512, rows = 3, frameWords = rowBytes * rows / 4;
  GuardedWords joined(2 * frameWords), scratch(rowBytes / 4);
  for (size_t i = 0; i < frameWords; ++i) joined.data()[i] = uint32_t(i) ^ 0xfeef1234u;
  const std::vector<uint32_t> sourceBefore(joined.data(), joined.data() + frameWords);
  expect(ws43b::copyFrameChecked(joined.bytes() + rowBytes * rows, joined.bytes(),
                                scratch.data(), scratch.byteSize(), rowBytes, rows),
         "adjacent non-overlapping frame ranges are allowed");
  expect(std::equal(sourceBefore.begin(), sourceBefore.end(), joined.data()) &&
             std::equal(sourceBefore.begin(), sourceBefore.end(), joined.data() + frameWords),
         "adjacent copy preserves source and copies destination");
  expect(joined.guardsIntact() && scratch.guardsIntact(), "adjacent copy preserves all guards");
}

void frameRelease() {
  expect(!ws43b::frameReleaseObserved(73, 73), "stale completed-frame snapshot cannot release");
  expect(!ws43b::frameReleaseObserved(74, 73), "one fresh completed-frame event cannot release");
  expect(ws43b::frameReleaseObserved(75, 73), "two fresh completed-frame events release");
  expect(ws43b::frameReleaseObserved(79, 73), "more than two fresh events release");
  expect(!ws43b::frameReleaseObserved(UINT32_MAX, UINT32_MAX), "equal counters near wrap cannot release");
  expect(!ws43b::frameReleaseObserved(0, UINT32_MAX), "one event across wrap cannot release");
  expect(ws43b::frameReleaseObserved(1, UINT32_MAX), "two events across wrap release");
  expect(ws43b::frameReleaseObserved(0, UINT32_MAX - 1), "second event at zero releases");
}
} // namespace

int main() {
  // Exhaustive RGB565 scaling: day is lossless; black stays black; channels do not brighten.
  for(unsigned p=0;p<65536;++p){
    expect(ws43b::dimRgb565(p,100)==p,"day identity");
    const auto q=ws43b::dimRgb565(p,30);
    expect((q>>11)<=(p>>11) && ((q>>5)&63)<=((p>>5)&63) && (q&31)<=(p&31),"dim channels");
  }
  alignas(4) uint32_t source[2]={0xfffff800,0x07e0001f},a[2]={},b[2]={},scratch[2]={};
  const uint32_t first=source[0];
  expect(ws43b::copyFrameChecked((uint8_t*)a,(uint8_t*)source,scratch,8,8,1,30),"night copy");
  expect(a[0]==((uint32_t(ws43b::dimRgb565(0xffff,30))<<16)|ws43b::dimRgb565(0xf800,30)),"correct channel order");
  expect(ws43b::copyFrameChecked((uint8_t*)b,(uint8_t*)source,scratch,8,8,1,30)&&a[0]==b[0]&&source[0]==first,"no cumulative dimming");
  expect(ws43b::copyFrameChecked((uint8_t*)a,(uint8_t*)source,scratch,8,8,1,100)&&a[0]==first,"full restoration");
  expect(!ws43b::copyFrameChecked((uint8_t*)a,(uint8_t*)source,scratch,8,8,1,101),"reject invalid scale");

  exerciseGeometry(800 * 2, 480); // Physical panel frame, row is not a multiple of 256 bytes.
  exerciseGeometry(256 * 2, 17);  // Exact 256-pixel rows, with an odd row count.
  exerciseGeometry(132, 7);       // Partial cache/block-sized rows remain fully copied.
  exerciseGeometry(4, 1);         // Smallest supported geometry.
  invalidArguments();
  adjacentRanges();
  frameRelease();
  std::cout << "PASS: " << checks << " native frame-copy/release checks; hardware unverified\n";
}
