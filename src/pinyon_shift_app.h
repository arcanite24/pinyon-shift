#pragma once

#include <atomic>
#include <memory>
#include <string>

#include <rex/kernel/xam/ui_provider.h>
#include <rex/ui/overlay/achievement_icon_cache.h>
#include <rex/rex_app.h>
#include <rex/ui/window_listener.h>

namespace pinyon_shift::config {
class HostConfig;
}
namespace pinyon_shift {
class SaveBackups;
}
namespace pinyon_shift::hostui {
class HostUi;
}

class PinyonShiftApp final : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;
  ~PinyonShiftApp() override;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& context);

 protected:
  void OnConfigurePaths(rex::PathConfig& paths) override;
  std::optional<rex::PathConfig> OnFinalizePaths(
      const rex::PathConfig& defaults,
      std::function<void(rex::PathConfig)> resume) override;
  void OnPostInitLogging() override;
  void OnConfigureFonts(ImFontAtlas* atlas) override;
  void OnConfigureStyle(ImGuiStyle& imgui_style, rex::ui::Style& ui_style) override;
  void OnPreSetup(rex::RuntimeConfig& config) override;
  void OnPostLoadXexImage() override;
  void OnPostSetup() override;
  void OnPreLaunchModule() override;
  void OnPostLaunchModule(rex::system::XThread* thread) override;
  bool ShouldStartModuleThread() override;
  void OnGuestThreadExit(rex::system::XThread* thread) override;
  bool OnWindowCloseRequested() override;
  void OnShutdown() override;
  // Achievements use the host UI: F7 toggles its list, unlocks show its
  // toast, so the ImGui overlay and toast are not created.
  std::unique_ptr<rex::ui::ImGuiDialog> CreateAchievementsOverlay() override;
  std::unique_ptr<rex::ui::AchievementNotificationDialog> CreateAchievementNotificationDialog()
      override {
    return nullptr;
  }

 private:
  void RecordShutdownOnce();
  void ToggleGameMenu();
  // Opens the settings screen unless it is open; UI thread.
  void OpenSettingsMenu();
  // Creates the host UI and installs its XAM dialogs once presentation is
  // ready; UI thread.
  bool EnsureHostUi();
  // NP-4.4 Hor+: the title's aspect for the window's (pinyon_shift_hor_plus).
  void UpdateHorPlus();
  // While the pause map is open under Hor+, present 16:9 letterboxed.
  void ApplyMapView(bool open);
  bool map_view_open_ = false;

  // Recomputes Hor+ when the window changes size.
  class ResizeListener final : public rex::ui::WindowListener {
   public:
    explicit ResizeListener(PinyonShiftApp& app) : app_(app) {}
    void OnResize(rex::ui::UISetupEvent&) override { app_.UpdateHorPlus(); }

   private:
    PinyonShiftApp& app_;
  };
  ResizeListener resize_listener_{*this};
  bool resize_listener_added_ = false;

  std::atomic_bool shutdown_recorded_{false};
  // Created on first use: the presenter and input system it needs exist only
  // after runtime setup.
  std::unique_ptr<pinyon_shift::hostui::HostUi> host_ui_;
  // The XAM message box and keyboard drawn by host_ui_ (NP-5.2).
  std::unique_ptr<rex::kernel::xam::XamUiProvider> xam_dialogs_;
  // Achievement icons for the unlock toast (the title's XDBF images).
  std::unique_ptr<rex::ui::AchievementIconCache> achievement_icons_;
  uint64_t achievement_listener_ = 0;
  std::unique_ptr<pinyon_shift::SaveBackups> save_backups_;
  // enabled_mods as the settings file had it at start (NP-7).
  std::string enabled_mods_;
  // The settings file the in-game settings screen edits.
  std::unique_ptr<pinyon_shift::config::HostConfig> host_config_;
};
