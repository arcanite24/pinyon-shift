#include "head_tracking/head_tracking.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#endif

#include <rex/logging.h>

REXCVAR_DEFINE_BOOL(head_tracking, false, "Pinyon Shift",
                    "Head tracking: turn and move the cockpit camera with OpenTrack's UDP "
                    "output (TrackIR, webcams, phones, VR headsets)");
REXCVAR_DEFINE_INT32(head_tracking_port, 4242, "Pinyon Shift",
                     "Head tracking: the UDP port OpenTrack sends to (its UDP over network "
                     "output, 4242 by default)")
    .range(1, 65535);
REXCVAR_DEFINE_STRING(head_tracking_invert, "", "Pinyon Shift",
                      "Head tracking: axes to reverse, any of yaw, pitch, roll, x, y, z "
                      "separated by commas");
REXCVAR_DEFINE_STRING(head_tracking_test_pose, "", "Pinyon Shift",
                      "Head tracking: a fixed pose for testing instead of OpenTrack, \"yaw, "
                      "pitch, roll, x, y, z\" in degrees and metres");

namespace pinyon_shift::head_tracking {

namespace {

#if defined(_WIN32)
using Socket = SOCKET;
constexpr Socket kNoSocket = INVALID_SOCKET;
void CloseSocket(Socket s) {
  closesocket(s);
}
#else
using Socket = int;
constexpr Socket kNoSocket = -1;
void CloseSocket(Socket s) {
  close(s);
}
#endif

// One thread, started the first time head tracking is on, follows the port
// the game thread asks for (0: none), so the game never waits on it.
struct Receiver {
  std::mutex mutex;
  Pose pose{};
  std::chrono::steady_clock::time_point received{};
  bool have_pose = false;
  std::atomic<int> port{0};
  std::atomic<bool> stop{false};
  std::thread thread;
  ~Receiver() {
    stop.store(true, std::memory_order_relaxed);
    if (thread.joinable())
      thread.join();
  }
};

Receiver& Shared() {
  static Receiver receiver;
  return receiver;
}

// A UDP socket on this PC only (OpenTrack runs beside the game, which also
// keeps the firewall from asking), waking every 100 ms to follow changes.
Socket Open(int port, bool report) {
  const Socket s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (s == kNoSocket) {
    if (report)
      REXLOG_WARN("Head tracking: cannot open a UDP socket");
    return kNoSocket;
  }
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_port = htons(uint16_t(port));
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (bind(s, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) != 0) {
    if (report)
      REXLOG_WARN("Head tracking: UDP port {} is in use, trying again every second", port);
    CloseSocket(s);
    return kNoSocket;
  }
#if defined(_WIN32)
  const DWORD timeout = 100;
#else
  const timeval timeout{0, 100000};
#endif
  setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&timeout), sizeof(timeout));
  REXLOG_INFO("Head tracking: listening for OpenTrack on UDP port {}", port);
  return s;
}

void Listen(Receiver* receiver) {
#if defined(_WIN32)
  WSADATA data;
  if (WSAStartup(MAKEWORD(2, 2), &data) != 0)
    return;
#endif
  using namespace std::chrono_literals;
  Socket s = kNoSocket;
  int bound = 0;
  // A port that would not bind is tried again each second, quietly.
  int failed = 0;
  auto retry = std::chrono::steady_clock::time_point{};
  uint8_t buffer[256];
  bool logged = false;
  while (!receiver->stop.load(std::memory_order_relaxed)) {
    const int port = receiver->port.load(std::memory_order_relaxed);
    if (s != kNoSocket && port != bound) {
      CloseSocket(s);
      s = kNoSocket;
      bound = 0;
    }
    if (port != failed)
      failed = 0;
    if (s == kNoSocket) {
      if (port == 0 || std::chrono::steady_clock::now() < retry) {
        std::this_thread::sleep_for(100ms);
        continue;
      }
      s = Open(port, port != failed);
      if (s == kNoSocket) {
        failed = port;
        retry = std::chrono::steady_clock::now() + 1s;
        continue;
      }
      bound = port;
      failed = 0;
      logged = false;
    }
    const auto size = recv(s, reinterpret_cast<char*>(buffer), int(sizeof(buffer)), 0);
    if (size <= 0)
      continue;
    const auto pose = ParseOpenTrack({buffer, size_t(size)});
    if (!pose)
      continue;
    if (!logged) {
      logged = true;
      REXLOG_INFO("Head tracking: receiving OpenTrack poses");
    }
    std::lock_guard lock(receiver->mutex);
    receiver->pose = *pose;
    receiver->received = std::chrono::steady_clock::now();
    receiver->have_pose = true;
  }
  if (s != kNoSocket)
    CloseSocket(s);
#if defined(_WIN32)
  WSACleanup();
#endif
}

std::optional<Pose> ParseTestPose(const std::string& text) {
  if (text.empty())
    return std::nullopt;
  Pose pose{};
  size_t start = 0;
  for (size_t i = 0; i < 6 && start <= text.size(); ++i) {
    const size_t end = std::min(text.find(',', start), text.size());
    try {
      pose[i] = std::stof(text.substr(start, end - start));
    } catch (...) {
      pose[i] = 0.0f;
    }
    start = end + 1;
  }
  return pose;
}

}  // namespace

std::optional<Pose> ParseOpenTrack(std::span<const uint8_t> packet) {
  if (packet.size() < 48)
    return std::nullopt;
  double v[6];
  std::memcpy(v, packet.data(), sizeof(v));
  auto finite = [](double x) { return std::isfinite(x) ? float(x) : 0.0f; };
  // OpenTrack: x, y, z (cm), yaw, pitch, roll (degrees).
  return Pose{finite(v[3]),          finite(v[4]),          finite(v[5]),
              finite(v[0]) / 100.0f, finite(v[1]) / 100.0f, finite(v[2]) / 100.0f};
}

std::array<bool, 6> ParseInvert(std::string_view text) {
  static constexpr std::string_view kNames[] = {"yaw", "pitch", "roll", "x", "y", "z"};
  std::array<bool, 6> invert{};
  size_t start = 0;
  while (start <= text.size()) {
    const size_t end = std::min(text.find(',', start), text.size());
    std::string_view name = text.substr(start, end - start);
    while (!name.empty() && name.front() == ' ')
      name.remove_prefix(1);
    while (!name.empty() && name.back() == ' ')
      name.remove_suffix(1);
    for (size_t i = 0; i < 6; ++i)
      invert[i] = invert[i] || name == kNames[i];
    start = end + 1;
  }
  return invert;
}

Pose Current() {
  if (!REXCVAR_GET(head_tracking))
    return {};
  Pose pose{};
  if (const auto test = ParseTestPose(REXCVAR_GET(head_tracking_test_pose))) {
    pose = *test;
  } else {
    auto& receiver = Shared();
    std::lock_guard lock(receiver.mutex);
    if (!receiver.have_pose)
      return {};
    const double age =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - receiver.received).count();
    // A tracker that stopped: hold for a second, then ease back to centre.
    const float keep = float(std::clamp(1.0 - (age - 1.0) / 0.5, 0.0, 1.0));
    for (size_t i = 0; i < 6; ++i)
      pose[i] = receiver.pose[i] * keep;
  }
  const auto invert = ParseInvert(REXCVAR_GET(head_tracking_invert));
  for (size_t i = 0; i < 6; ++i) {
    if (invert[i])
      pose[i] = -pose[i];
  }
  return pose;
}

void Update() {
  auto& receiver = Shared();
  const bool wanted = REXCVAR_GET(head_tracking) && REXCVAR_GET(head_tracking_test_pose).empty();
  receiver.port.store(wanted ? REXCVAR_GET(head_tracking_port) : 0, std::memory_order_relaxed);
  if (wanted && !receiver.thread.joinable())
    receiver.thread = std::thread(Listen, &receiver);
}

}  // namespace pinyon_shift::head_tracking
