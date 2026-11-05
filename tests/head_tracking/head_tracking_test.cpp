#include <chrono>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <thread>

#if defined(_WIN32)
#include <winsock2.h>
#else
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include "head_tracking/head_tracking.h"

using namespace pinyon_shift::head_tracking;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "%d: %s\n", __LINE__, #c); ++failures; } } while (false)

#if defined(_WIN32)
using Socket = SOCKET;
static void CloseSocket(Socket s) { closesocket(s); }
#else
using Socket = int;
static void CloseSocket(Socket s) { close(s); }
#endif

// A port another program holds: the receiver keeps trying, and picks up
// OpenTrack's packets once the port is free, without the game thread
// waiting on it.
static void ReceiverRetriesABusyPort() {
#if defined(_WIN32)
  WSADATA data;
  CHECK(WSAStartup(MAKEWORD(2, 2), &data) == 0);
#endif
  constexpr int kPort = 47421;
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_port = htons(kPort);
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  const Socket holder = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  CHECK(bind(holder, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) == 0);

  rex::cvar::SetFlagByName("head_tracking_port", std::to_string(kPort));
  rex::cvar::SetFlagByName("head_tracking", "true");
  const auto start = std::chrono::steady_clock::now();
  Update();
  CHECK(std::chrono::steady_clock::now() - start < std::chrono::milliseconds(20));
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  CloseSocket(holder);

  const double values[6] = {0.0, 0.0, 0.0, 20.0, 0.0, 0.0};
  const Socket sender = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  bool received = false;
  for (int i = 0; i < 40 && !received; ++i) {
    sendto(sender, reinterpret_cast<const char*>(values), int(sizeof(values)), 0,
           reinterpret_cast<const sockaddr*>(&address), sizeof(address));
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    received = Current()[kYaw] == 20.0f;
  }
  CHECK(received);
  CloseSocket(sender);

  rex::cvar::SetFlagByName("head_tracking", "false");
  const auto stop = std::chrono::steady_clock::now();
  Update();
  CHECK(std::chrono::steady_clock::now() - stop < std::chrono::milliseconds(20));
  CHECK(Current() == Pose{});
}

int main() {
  // OpenTrack: x, y, z in cm, then yaw, pitch, roll in degrees.
  const double values[6] = {2.0, -3.0, 50.0, 30.0, -10.0, 5.0};
  uint8_t packet[48];
  std::memcpy(packet, values, sizeof(packet));
  const auto pose = ParseOpenTrack(packet);
  CHECK(pose.has_value());
  if (pose) {
    CHECK((*pose)[kYaw] == 30.0f && (*pose)[kPitch] == -10.0f && (*pose)[kRoll] == 5.0f);
    CHECK((*pose)[kX] == 0.02f && (*pose)[kY] == -0.03f && (*pose)[kZ] == 0.5f);
  }
  CHECK(!ParseOpenTrack({packet, 40}));
  const double bad[6] = {std::numeric_limits<double>::quiet_NaN(), 0, 0,
                         std::numeric_limits<double>::infinity(), 0, 0};
  std::memcpy(packet, bad, sizeof(packet));
  const auto cleaned = ParseOpenTrack(packet);
  CHECK(cleaned && (*cleaned)[kX] == 0.0f && (*cleaned)[kYaw] == 0.0f);

  const auto invert = ParseInvert("yaw, z,bogus");
  CHECK(invert[kYaw] && invert[kZ] && !invert[kPitch] && !invert[kRoll] && !invert[kX]);
  CHECK(ParseInvert("") == (std::array<bool, 6>{}));

  ReceiverRetriesABusyPort();

  if (failures) {
    std::fprintf(stderr, "%d failure(s)\n", failures);
    return 1;
  }
  std::printf("head tracking tests passed\n");
  return 0;
}
