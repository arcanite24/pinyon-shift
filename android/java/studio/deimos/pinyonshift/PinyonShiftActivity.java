package studio.deimos.pinyonshift;

import android.app.Dialog;
import android.content.BroadcastReceiver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.res.AssetManager;
import android.database.Cursor;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.os.FileObserver;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.system.ErrnoException;
import android.system.Os;
import android.util.DisplayMetrics;
import android.util.Log;
import android.util.TypedValue;
import android.view.Display;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.Surface;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public class PinyonShiftActivity extends SDLActivity implements View.OnClickListener {
    private static final String TAG = "PinyonShift";
    private static final int REQUEST_GPU_DRIVER_ZIP = 0x5053;
    private File driversDir;

    public static final int BTN_DPAD_UP = 0x0001, BTN_DPAD_DOWN = 0x0002, BTN_DPAD_LEFT = 0x0004, BTN_DPAD_RIGHT = 0x0008;
    public static final int BTN_START = 0x0010, BTN_BACK = 0x0020, BTN_LEFT_SHOULDER = 0x0100, BTN_RIGHT_SHOULDER = 0x0200;
    public static final int BTN_A = 0x1000, BTN_B = 0x2000, BTN_X = 0x4000, BTN_Y = 0x8000;
    public static final String PREF_SMART_CLUTCH = "pref_smart_clutch", PREF_GESTURE_SHIFT = "pref_gesture_shift", PREF_HUD_HITBOXES = "pref_hud_hitboxes", PREF_MENU_MODE_AUTO = "pref_menu_mode_auto", PREF_LOOK_AROUND = "pref_look_around", PREF_ASPECT_MODE = "pref_aspect_mode";
    public static final String PREF_TOUCH_OVERLAY_ENABLED = "pref_touch_overlay_enabled";

    public static native void nativeSetPadState(float steer, float throttle, float brake, float lookX, float lookY, int buttons);
    public static native void nativeAction(int actionId, float value);
    public static native void nativeSetMobileOverrides(float steer_x, float throttle, float brake, int button_mask, float look_x, float look_y, float steer_y);
    public static native void nativeSetCVar(String name, String value);
    public static native float nativeGetFrameTimeMs();

    private SharedPreferences prefs;
    private RR3OverlayView rr3Overlay;
    private View quickHudDrawer;
    private SensorManager sensorManager;
    private Sensor gameRotationSensor;
    private float baselineRoll = 0.0f, currentTiltDegrees = 0.0f;
    private boolean gyroCalibrated = false, autoThrottle = false, inMenuMode = false, showFpsOverlay = true, thermalPacerEnabled = true;
    private boolean touchOverlayEnabled = false;
    private String controlScheme = "arrows";
    private int steerYPct = 65, steerXDp = 65;
    private TextView hudTempText;
    private volatile float currentSteerX = 0.0f, currentSteerY = 0.0f, currentThrottle = 0.0f, currentBrake = 0.0f, currentLookX = 0.0f, currentLookY = 0.0f;
    private volatile int currentButtons = 0;
    private BroadcastReceiver thermalReceiver;
    private float currentBatteryTempC = 25.0f;
    private int currentFpsTarget = 30;
    private FileObserver photoObserver;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        File external = getExternalFilesDir(null);
        File base = external != null ? external : getFilesDir();
        setDefaultEnvironment("HOME", getFilesDir().getAbsolutePath());
        setDefaultEnvironment("PINYON_SHIFT_STATE_ROOT",
                new File(base, "state").getAbsolutePath());
        setDefaultEnvironment("PINYON_SHIFT_GAME_ROOT",
                new File(base, "game/base").getAbsolutePath());
        // Custom GPU drivers (Mesa Turnip) the player copied in, chosen with
        // android_gpu_driver; the runtime copies the chosen one inside.
        driversDir = new File(base, "state/drivers");
        setDefaultEnvironment("REX_ANDROID_DRIVERS_DIR", driversDir.getAbsolutePath());
        // Drivers packaged with the game (Mesa Turnip builds known to work),
        // and the one recommended for this GPU, which android_gpu_driver
        // "auto" (the default) loads.
        installBundledDrivers();
        String adreno = adrenoModel();
        if (adreno != null) {
            setDefaultEnvironment("PINYON_SHIFT_ADRENO_MODEL", adreno);
            String recommended = recommendedDriver(adreno);
            if (recommended != null) {
                setDefaultEnvironment("REX_ANDROID_RECOMMENDED_DRIVER", recommended);
            }
        }
        // Rally, once tools/prepare-fh1-rally.py's overlay was copied into
        // state/cache (the PC launcher verifies it before the same flag);
        // the game still checks the enabled package and the stage mapping.
        if (new File(base, "state/cache/rally_adapter/rally-stage.toml").isFile()) {
            setDefaultEnvironment("PINYON_SHIFT_RALLY_PREPARED", "1");
        }
        applyPendingMods(base);
        // The build's provenance, packaged as an asset, for logs and crash
        // reports (the game reads it beside the executable elsewhere).
        File manifest = new File(getFilesDir(), "pinyon_shift_build.json");
        try (InputStream in = getAssets().open("pinyon_shift_build.json");
             OutputStream out = new FileOutputStream(manifest)) {
            byte[] buffer = new byte[8192];
            for (int read; (read = in.read(buffer)) > 0; ) {
                out.write(buffer, 0, read);
            }
            setEnvironment("PINYON_SHIFT_BUILD_MANIFEST", manifest.getAbsolutePath());
        } catch (IOException error) {
            Log.w(TAG, "no build manifest in the package", error);
        }
        Intent intent = getIntent();
        Bundle extras = intent != null ? intent.getExtras() : null;
        if (extras != null) {
            for (String key : extras.keySet()) {
                if (key.startsWith("env.")) {
                    Object value = extras.get(key);
                    if (value != null) {
                        setEnvironment(key.substring(4), value.toString());
                    }
                }
            }
        }
        recordDisplayEnvironment();
        super.onCreate(savedInstanceState);
        // A race played on a controller touches nothing, and a screen that
        // times out sends the game to the background, where it pauses (a
        // scripted route stalls the same way). Only while this window shows.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        // Scripted routes started from the PC: over the lock screen, with the
        // screen on, so a device that slept between runs does not hold the
        // game behind the lock. A launch from the home screen never asks.
        if (getIntent().getBooleanExtra("show_when_locked", false)) {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
        }
        initOverlayAndControls(base);
    }

    // Native logging survives ROMs which silence logcat. This is a launch
    // snapshot, not a measurement of the panel's HDR output.
    private void recordDisplayEnvironment() {
        Display display = getDisplay();
        if (display == null) return;
        Display.Mode mode = display.getMode();
        setEnvironment("REX_ANDROID_DISPLAY_DIAGNOSTICS", String.format(Locale.ROOT,
                "%s / Android %s; display=%d mode=%d %dx%d@%.2f rotation=%d; "
                        + "brightness=%d brightness_mode=%d window_brightness=%.3f color_mode=%d",
                Build.MODEL, Build.VERSION.RELEASE, display.getDisplayId(), mode.getModeId(),
                mode.getPhysicalWidth(), mode.getPhysicalHeight(), mode.getRefreshRate(),
                display.getRotation(),
                Settings.System.getInt(getContentResolver(), Settings.System.SCREEN_BRIGHTNESS, -1),
                Settings.System.getInt(getContentResolver(), Settings.System.SCREEN_BRIGHTNESS_MODE, -1),
                getWindow().getAttributes().screenBrightness, getWindow().getColorMode()));
    }

    // The C++ runtime first, then the ReXGlue runtime, which holds SDL and
    // registers its Java natives when loaded, then the game (libmain.so),
    // whose SDL_main SDL calls.
    @Override
    protected String[] getLibraries() {
        return new String[] {"c++_shared", "rexruntime", "main"};
    }

    // The native libraries are built for ARMv8.2-A (NN-1.11): an older core
    // would crash on the first LSE atomic, possibly in a library's static
    // initializer. SDL shows a link error from here as a dialog instead.
    @Override
    public void loadLibraries() {
        if (!cpuHasFeatures("atomics", "asimdrdm")) {
            throw new UnsatisfiedLinkError("Pinyon Shift needs an ARMv8.2 CPU "
                    + "(Cortex-A55, Cortex-A75 or newer); this device's CPU is older.");
        }
        super.loadLibraries();
    }

    // Whether the kernel lists every given feature for the CPU. True when
    // /proc/cpuinfo cannot be read, so an unusual kernel does not lock out a
    // CPU that would run the game.
    private static boolean cpuHasFeatures(String... features) {
        try (BufferedReader reader = new BufferedReader(new FileReader("/proc/cpuinfo"))) {
            for (String line; (line = reader.readLine()) != null; ) {
                if (!line.startsWith("Features")) continue;
                List<String> listed = java.util.Arrays.asList(line.substring(line.indexOf(':') + 1).trim().split("\\s+"));
                for (String feature : features) {
                    if (!listed.contains(feature)) return false;
                }
                return true;
            }
        } catch (IOException ignored) {
            // Unreadable: let the libraries load.
        }
        return true;
    }

    // The intent's args, then the lines of state/config/android-arguments.txt,
    // which the setup screen writes (1000 Club offline with title update v4).
    @Override
    protected String[] getArguments() {
        Intent intent = getIntent();
        String[] given = intent != null ? intent.getStringArrayExtra("args") : null;
        List<String> arguments = new ArrayList<>();
        if (given != null) Collections.addAll(arguments, given);
        File external = getExternalFilesDir(null);
        File file = new File(external != null ? external : getFilesDir(), SetupActivity.ARGUMENTS_FILE);
        if (file.isFile()) {
            try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
                for (String line; (line = reader.readLine()) != null; ) {
                    if (line.trim().startsWith("--")) arguments.add(line.trim());
                }
            } catch (IOException error) {
                Log.w(TAG, "launch arguments not read", error);
            }
        }
        return arguments.toArray(new String[0]);
    }

    // enabled_mods from a mod set the setup screen copied before the game had
    // written its settings file; the game reads the list at start.
    private static void applyPendingMods(File base) {
        File pending = new File(base, SetupActivity.PENDING_MODS_FILE);
        File config = new File(base, SetupActivity.CONFIG_FILE);
        if (!pending.isFile() || !config.isFile()) return;
        try (BufferedReader reader = new BufferedReader(new FileReader(pending))) {
            String mods = reader.readLine();
            SetupActivity.applyEnabledMods(config, mods != null ? mods.trim() : "");
            if (!pending.delete()) Log.w(TAG, "pending mods not removed");
        } catch (IOException error) {
            Log.w(TAG, "pending mods not applied", error);
        }
    }

    // The Adreno GPU's model number ("740"), from the kernel driver, or from
    // the SoC where that is not readable; null when not an Adreno.
    private static String adrenoModel() {
        try (BufferedReader reader = new BufferedReader(
                new FileReader("/sys/class/kgsl/kgsl-3d0/gpu_model"))) {
            String line = reader.readLine();
            Matcher match = line != null ? Pattern.compile("Adreno(\\d{3})").matcher(line) : null;
            if (match != null && match.find()) {
                return match.group(1);
            }
        } catch (IOException ignored) {
            // Not readable here: the SoC below.
        }
        if (Build.VERSION.SDK_INT >= 31) {
            switch (Build.SOC_MODEL) {
                case "SM8450": case "SM8475": return "730";
                case "SM8550": case "QCS8550": return "740";
                case "SM8635": return "735";
                case "SM8650": return "750";
                case "SM7475": return "725";
                case "SM7550": return "720";
                case "SM7675": return "732";
                case "SM8750": return "830";
                default: break;
            }
        }
        return null;
    }

    // Adreno 7xx and 8xx: Mesa Turnip Gen8 V37 (measured on the Adreno 740
    // and 830 against the system driver, and on the 740 against newer Turnip
    // builds). Others keep the system's.
    private static String recommendedDriver(String adreno) {
        return adreno.startsWith("7") || adreno.startsWith("8") ? "turnip-gen8-v37" : null;
    }

    // Copies each driver folder under the package's assets/drivers into
    // state/drivers, where a file is missing or differs in size.
    private void installBundledDrivers() {
        try {
            String[] names = getAssets().list("drivers");
            if (names == null) return;
            for (String name : names) {
                String[] files = getAssets().list("drivers/" + name);
                if (files == null || files.length == 0) continue;
                File folder = new File(driversDir, name);
                folder.mkdirs();
                for (String file : files) {
                    File target = new File(folder, file);
                    long size;
                    try (InputStream in = getAssets().open("drivers/" + name + "/" + file)) {
                        size = 0;
                        byte[] buffer = new byte[65536];
                        for (int read; (read = in.read(buffer)) > 0; ) size += read;
                    }
                    if (target.length() == size) continue;
                    try (InputStream in = getAssets().open("drivers/" + name + "/" + file);
                         OutputStream out = new FileOutputStream(target)) {
                        copy(in, out);
                    }
                    Log.i(TAG, "bundled GPU driver " + name + ": " + file + " installed");
                }
            }
        } catch (IOException error) {
            Log.w(TAG, "bundled GPU drivers not installed", error);
        }
    }

    private static void copy(InputStream in, OutputStream out) throws IOException {
        byte[] buffer = new byte[65536];
        for (int read; (read = in.read(buffer)) > 0; ) {
            out.write(buffer, 0, read);
        }
    }

    // SETTINGS > GRAPHICS > IMPORT DRIVER (.ZIP): the system document picker,
    // then the chosen adrenotools package unpacked into state/drivers.
    // Called from the game's native thread.
    public void importGpuDriver() {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[] {"application/zip",
                        "application/x-zip-compressed", "application/octet-stream"});
                try {
                    startActivityForResult(intent, REQUEST_GPU_DRIVER_ZIP);
                } catch (Exception error) {
                    Log.e(TAG, "no document picker", error);
                    toast("No file picker available on this device");
                }
            }
        });
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode != REQUEST_GPU_DRIVER_ZIP) {
            super.onActivityResult(requestCode, resultCode, data);
            return;
        }
        if (resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        final Uri uri = data.getData();
        new Thread(new Runnable() {
            @Override
            public void run() {
                String result;
                try {
                    result = "GPU driver " + unpackDriver(uri)
                            + " imported: choose it in SETTINGS > GRAPHICS > GPU DRIVER and restart";
                } catch (IOException error) {
                    Log.e(TAG, "GPU driver import failed", error);
                    result = "GPU driver not imported: " + error.getMessage();
                }
                toast(result);
            }
        }, "GpuDriverImport").start();
    }

    // Unpacks an adrenotools driver zip (meta.json and the driver .so, the
    // files at any depth) into state/drivers/<the zip's name>.
    private String unpackDriver(Uri uri) throws IOException {
        String display = "driver";
        try (Cursor cursor = getContentResolver().query(uri,
                new String[] {OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst() && !cursor.isNull(0)) {
                display = cursor.getString(0);
            }
        }
        String name = display.replaceAll("(?i)\\.zip$", "")
                .replaceAll("[^A-Za-z0-9._-]+", "-").toLowerCase(Locale.ROOT);
        if (name.isEmpty() || name.startsWith(".")) name = "driver";
        File folder = new File(driversDir, name);
        File staging = new File(driversDir, "." + name + ".importing");
        deleteTree(staging);
        staging.mkdirs();
        boolean library = false;
        try (InputStream in = getContentResolver().openInputStream(uri);
             ZipInputStream zip = new ZipInputStream(in)) {
            for (ZipEntry entry; (entry = zip.getNextEntry()) != null; ) {
                if (entry.isDirectory()) continue;
                String file = new File(entry.getName()).getName();
                if (file.isEmpty() || file.startsWith(".")) continue;
                library |= file.endsWith(".so");
                try (OutputStream out = new FileOutputStream(new File(staging, file))) {
                    copy(zip, out);
                }
            }
        }
        if (!library) {
            deleteTree(staging);
            throw new IOException("the zip holds no driver library (.so)");
        }
        deleteTree(folder);
        if (!staging.renameTo(folder)) {
            throw new IOException("cannot create " + folder);
        }
        return name;
    }

    private static void deleteTree(File file) {
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) deleteTree(child);
        }
        file.delete();
    }

    private void toast(final String text) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                Toast.makeText(PinyonShiftActivity.this, text, Toast.LENGTH_LONG).show();
            }
        });
    }

    private int lastRumbleLeft = -1;
    private int lastRumbleRight = -1;
    private long lastRumbleTimeMs = 0;

    public void onRumble(final int left, final int right) {
        if (left == 0 && right == 0) {
            if (lastRumbleLeft == 0 && lastRumbleRight == 0) return;
            lastRumbleLeft = 0;
            lastRumbleRight = 0;
            return;
        }

        final long now = SystemClock.uptimeMillis();
        // Rate-limit haptic calls to at most once per 40ms unless motor intensity shifted substantially (>20%).
        final boolean intensityChanged = Math.abs(left - lastRumbleLeft) > 13000
                || Math.abs(right - lastRumbleRight) > 13000;
        if (!intensityChanged && (now - lastRumbleTimeMs < 40)) {
            return;
        }

        lastRumbleLeft = left;
        lastRumbleRight = right;
        lastRumbleTimeMs = now;

        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                pulseHaptic((left > 32768 || right > 32768) ? 0 : 3);
            }
        });
    }

    public void pulseHaptic(int constant) {
        if (mLayout != null) {
            mLayout.setHapticFeedbackEnabled(true);
            mLayout.performHapticFeedback(constant, 3);
        }
        try {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v != null && v.hasVibrator()) {
                if (Build.VERSION.SDK_INT >= 29) {
                    VibrationEffect eff = VibrationEffect.createPredefined(
                            constant == 0 ? VibrationEffect.EFFECT_HEAVY_CLICK : VibrationEffect.EFFECT_CLICK);
                    try {
                        Object b = Class.forName("android.os.VibrationAttributes$Builder").getDeclaredConstructor().newInstance();
                        b.getClass().getMethod("setUsage", int.class).invoke(b, 33);
                        Object attr = b.getClass().getMethod("build").invoke(b);
                        v.getClass().getMethod("vibrate", VibrationEffect.class, Class.forName("android.os.VibrationAttributes")).invoke(v, eff, attr);
                    } catch (Throwable t) {
                        v.vibrate(eff);
                    }
                } else {
                    v.vibrate(constant == 0 ? 30 : 15);
                }
            }
        } catch (Throwable ignored) {}
    }

    private static void setDefaultEnvironment(String name, String value) {
        if (Os.getenv(name) == null) {
            setEnvironment(name, value);
        }
    }

    private static void setEnvironment(String name, String value) {
        try {
            Os.setenv(name, value, true);
        } catch (ErrnoException error) {
            Log.e(TAG, "setenv " + name + " failed", error);
        }
    }


    private void initOverlayAndControls(File base) {
        prefs = getSharedPreferences("pinyon_shift_settings", MODE_PRIVATE);
        touchOverlayEnabled = prefs.getBoolean(PREF_TOUCH_OVERLAY_ENABLED, true);
        controlScheme = prefs.getString("control_scheme", "arrows");
        steerYPct = prefs.getInt("steer_y_pct", 65);
        steerXDp = prefs.getInt("steer_x_dp", 65);
        autoThrottle = prefs.getBoolean("auto_throttle", false);
        showFpsOverlay = prefs.getBoolean("fps_overlay", true);
        thermalPacerEnabled = prefs.getBoolean("thermal_pacer", true);
        if (autoThrottle) currentThrottle = 1.0f;

        enforceCutoutMode();
        int res = prefs.getInt("res_scale", 1080);
        if (res <= 540) { res = 1080; prefs.edit().putInt("res_scale", 1080).apply(); }
        applySurfaceResolution(res);
        applyBrightness(prefs.getInt("screen_brightness", 100));
        initSensors();
        initThermalPacer();
        File photosDir = new File(base, "state/photos");
        startPhotoWatcher(photosDir);

        if (touchOverlayEnabled) {
            attachMobileOverlays();
        }
    }

    private void enforceCutoutMode() {
        if (getWindow() == null) return;
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (Build.VERSION.SDK_INT >= 28) {
            WindowManager.LayoutParams lp = getWindow().getAttributes();
            lp.layoutInDisplayCutoutMode = Build.VERSION.SDK_INT >= 30
                    ? WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
                    : WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            getWindow().setAttributes(lp);
            if (Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        }
        if (mLayout != null) mLayout.setFitsSystemWindows(false);
        if (mSurface != null) mSurface.setFitsSystemWindows(false);
    }

    private void applySurfaceResolution(int s) {
        if (mSurface == null) return;
        ViewGroup.LayoutParams lp = mSurface.getLayoutParams();
        if (lp != null) {
            lp.width = lp.height = ViewGroup.LayoutParams.MATCH_PARENT;
            mSurface.setLayoutParams(lp);
        }
        if (s == 720) {
            DisplayMetrics dm = getResources().getDisplayMetrics();
            float asp = (float) Math.max(dm.widthPixels, dm.heightPixels) / (float) Math.max(1, Math.min(dm.widthPixels, dm.heightPixels));
            mSurface.getHolder().setFixedSize(Math.round(720 * asp), 720);
        } else {
            mSurface.getHolder().setSizeFromLayout();
        }
    }

    private void applyBrightness(int b) {
        if (getWindow() == null) return;
        WindowManager.LayoutParams lp = getWindow().getAttributes();
        lp.screenBrightness = (b <= 0) ? -1.0f : Math.max(0.05f, Math.min(1.0f, b / 100.0f));
        getWindow().setAttributes(lp);
    }

    private void confirmQuit() {
        final Dialog d = new Dialog(this);
        d.requestWindowFeature(Window.FEATURE_NO_TITLE);
        if (d.getWindow() != null) d.getWindow().setBackgroundDrawable(new ColorDrawable(0));
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setPadding(dp(18), dp(18), dp(18), dp(14));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xFF181D1A);
        bg.setCornerRadius(dp(18));
        bg.setStroke(dp(1), 0xFF26302A);
        c.setBackground(bg);
        TextView tv = new TextView(this);
        tv.setText("Quit Game\nExit to launcher?");
        tv.setTextColor(Color.WHITE);
        tv.setTypeface(Typeface.DEFAULT_BOLD);
        c.addView(tv);
        LinearLayout row = new LinearLayout(this);
        Button cancel = createChipButton("Cancel", false);
        cancel.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { d.dismiss(); }
        });
        Button quit = createChipButton("Quit", true);
        quit.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                d.dismiss();
                finish();
            }
        });
        row.addView(cancel, new LinearLayout.LayoutParams(0, -2, 1.0f));
        row.addView(new View(this), new LinearLayout.LayoutParams(dp(10), 1));
        row.addView(quit, new LinearLayout.LayoutParams(0, -2, 1.0f));
        c.addView(row);
        d.setContentView(c);
        d.show();
    }

    @Override
    public void onBackPressed() {
        if (quickHudDrawer != null && quickHudDrawer.getVisibility() == View.VISIBLE) {
            toggleQuickHud();
            return;
        }
        if (touchOverlayEnabled && inMenuMode) {
            confirmQuit();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onResume() {
        super.onResume();
        enforceCutoutMode();
        if (Build.VERSION.SDK_INT >= 30) {
            try { SDLActivity.onNativeInsetsChanged(0, 0, 0, 0); } catch (Throwable ignored) {}
        }
        if (prefs != null) {
            int res = prefs.getInt("res_scale", 1080);
            if (res <= 540) { res = 1080; prefs.edit().putInt("res_scale", 1080).apply(); }
            applySurfaceResolution(res);
            applyBrightness(prefs.getInt("screen_brightness", 100));
            applyDisplayRefreshRate(currentFpsTarget);
            boolean gyroOn = isGyroActive();
            if (sensorManager != null && gameRotationSensor != null && gyroOn) {
                sensorManager.registerListener(sensorListener, gameRotationSensor, SensorManager.SENSOR_DELAY_GAME);
            }
            String asp = prefs.getString(PREF_ASPECT_MODE, "hor_plus");
            try { nativeAction(4, "hor_plus".equals(asp) ? 1.0f : 0.0f); } catch (UnsatisfiedLinkError ignored) {}
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            enforceCutoutMode();
            if (Build.VERSION.SDK_INT >= 30) {
                try { SDLActivity.onNativeInsetsChanged(0, 0, 0, 0); } catch (Throwable ignored) {}
            }
        }
    }

    private void applyDisplayRefreshRate(int targetFps) {
        if (Build.VERSION.SDK_INT >= 30) {
            if (getWindow() != null) {
                WindowManager.LayoutParams p = getWindow().getAttributes();
                p.preferredRefreshRate = (targetFps == 120) ? 120.0f : 60.0f;
                getWindow().setAttributes(p);
            }
            if (mSurface != null && mSurface.getHolder() != null && mSurface.getHolder().getSurface() != null) {
                try {
                    mSurface.getHolder().getSurface().setFrameRate((float) targetFps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE);
                } catch (Throwable ignored) {}
            }
        }
    }

    @Override
    protected void onPause() {
        if (sensorManager != null) {
            sensorManager.unregisterListener(sensorListener);
        }
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (thermalReceiver != null) {
            try { unregisterReceiver(thermalReceiver); } catch (Exception ignored) {}
        }
        if (photoObserver != null) {
            photoObserver.stopWatching();
        }
        super.onDestroy();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (touchOverlayEnabled && event.getAction() == KeyEvent.ACTION_DOWN) {
            int c = event.getKeyCode();
            if (c == KeyEvent.KEYCODE_BACK) {
                inMenuMode = !inMenuMode;
                pulseButton(inMenuMode ? BTN_START : BTN_B, 120);
                if (rr3Overlay != null) rr3Overlay.postInvalidate();
                return true;
            }
            int b = c == 19 ? BTN_DPAD_UP : c == 20 ? BTN_DPAD_DOWN : c == 21 ? BTN_DPAD_LEFT : c == 22 ? BTN_DPAD_RIGHT
                    : (c == 96 || c == 66 || c == 62) ? BTN_A : c == 97 ? BTN_B : c == 99 ? BTN_X : c == 100 ? BTN_Y : c == 108 ? BTN_START : 0;
            if (b != 0) {
                pulseButton(b, 120);
                return true;
            }
        }
        return super.dispatchKeyEvent(event);
    }

    private void flushOverrides() {
        if (!touchOverlayEnabled) return;
        try {
            nativeSetPadState(currentSteerX, currentThrottle, currentBrake, currentLookX, currentLookY, currentButtons);
        } catch (UnsatisfiedLinkError ignored) {}
    }

    private void pulseButton(final int mask, int durationMs) {
        currentButtons |= mask;
        flushOverrides();
        pulseHaptic(3);
        mainHandler.postDelayed(new Runnable() {
            @Override public void run() {
                currentButtons &= ~mask;
                flushOverrides();
                if (rr3Overlay != null) rr3Overlay.postInvalidate();
            }
        }, Math.max(50, durationMs));
    }

    private void triggerShift(final boolean shiftUp) {
        final int shiftBtn = shiftUp ? BTN_B : BTN_X;
        if (prefs != null && prefs.getBoolean(PREF_SMART_CLUTCH, true)) {
            currentButtons |= BTN_LEFT_SHOULDER;
            flushOverrides();
            pulseHaptic(3);
            mainHandler.postDelayed(new Runnable() {
                @Override public void run() { currentButtons |= shiftBtn; flushOverrides(); }
            }, 40);
            mainHandler.postDelayed(new Runnable() {
                @Override public void run() { currentButtons &= ~(BTN_LEFT_SHOULDER | shiftBtn); flushOverrides(); }
            }, 80);
        } else {
            pulseButton(shiftBtn, 90);
        }
    }

    private void initSensors() {
        sensorManager = (SensorManager) getSystemService(Context.SENSOR_SERVICE);
        if (sensorManager != null) {
            gameRotationSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR);
            if (gameRotationSensor == null) gameRotationSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR);
        }
    }

    private final SensorEventListener sensorListener = new SensorEventListener() {
        private final float[] rotationMatrix = new float[9];
        private final float[] orientationAngles = new float[3];
        @Override
        public void onSensorChanged(SensorEvent event) {
            if (!isGyroActive() || inMenuMode) return;
            SensorManager.getRotationMatrixFromVector(rotationMatrix, event.values);
            float[] remapped = new float[9];
            int rot = 0;
            try { rot = getWindowManager().getDefaultDisplay().getRotation(); } catch (Throwable ignored) {}
            if (rot == Surface.ROTATION_90) SensorManager.remapCoordinateSystem(rotationMatrix, SensorManager.AXIS_Y, SensorManager.AXIS_MINUS_X, remapped);
            else if (rot == Surface.ROTATION_270) SensorManager.remapCoordinateSystem(rotationMatrix, SensorManager.AXIS_MINUS_Y, SensorManager.AXIS_X, remapped);
            else System.arraycopy(rotationMatrix, 0, remapped, 0, 9);
            SensorManager.getOrientation(remapped, orientationAngles);
            float rollDeg = (float) Math.toDegrees(orientationAngles[2]);
            if (!gyroCalibrated) {
                baselineRoll = rollDeg;
                gyroCalibrated = true;
            }
            float delta = rollDeg - baselineRoll;
            if (delta > 180.0f) delta -= 360.0f;
            if (delta < -180.0f) delta += 360.0f;
            currentTiltDegrees = delta;
            if (rr3Overlay != null) rr3Overlay.setTiltAngle(currentTiltDegrees);
            if (rr3Overlay != null && rr3Overlay.touchSteerActive) return;
            float deadband = 2.0f, maxAngle = 30.0f, steer = 0.0f;
            if (Math.abs(delta) > deadband) {
                float eff = Math.min(1.0f, (Math.abs(delta) - deadband) / (maxAngle - deadband));
                steer = Math.copySign((float) Math.pow(eff, 1.3), delta);
            }
            currentSteerX = steer;
            flushOverrides();
        }
        @Override
        public void onAccuracyChanged(Sensor sensor, int accuracy) {}
    };

    private boolean isGyroActive() {
        return "tilt_a".equals(controlScheme) && prefs != null && prefs.getBoolean("experimental_gyro", false);
    }

    public void recalibrateGyro() {
        gyroCalibrated = false;
        toast("Gyro baseline zeroed to current position");
    }

    private void attachMobileOverlays() {
        runOnUiThread(new Runnable() {
            @Override public void run() {
                ViewGroup content = findViewById(android.R.id.content);
                if (content == null) return;
                rr3Overlay = new RR3OverlayView(PinyonShiftActivity.this);
                content.addView(rr3Overlay, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
                quickHudDrawer = createQuickHudDrawer();
                quickHudDrawer.setVisibility(View.GONE);
                content.addView(quickHudDrawer);
            }
        });
    }

    private View bindClick(View v, Object tag) {
        v.setTag(tag);
        v.setOnClickListener(this);
        return v;
    }

    private void addToggle(LinearLayout p, String text, boolean active, String tag) {
        p.addView(bindClick(createChipButton(text, active), tag));
    }

    private void addSwitch(LinearLayout p, String name, boolean val, String tag) {
        addToggle(p, name + ": " + (val ? "ON" : "OFF"), val, tag);
    }

    private void addHudRow(LinearLayout items, String title, String[] labels, String[] tags, int activeIdx) {
        addHudSectionTitle(items, title);
        LinearLayout row = new LinearLayout(this);
        for (int i = 0; i < labels.length; i++) {
            row.addView(bindClick(createChipButton(labels[i], i == activeIdx), tags[i]),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1.0f));
        }
        items.addView(row);
    }

    private void toggleQuickHud() {
        if (quickHudDrawer == null) return;
        boolean show = quickHudDrawer.getVisibility() != View.VISIBLE;
        if (show) {
            readBatteryTemp(registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED)));
            if (hudTempText != null) hudTempText.setText(String.format(Locale.ROOT, "Battery Temp: %.1f°C", currentBatteryTempC));
            quickHudDrawer.bringToFront();
        }
        quickHudDrawer.setVisibility(show ? View.VISIBLE : View.GONE);
    }

    private View createQuickHudDrawer() {
        int accent = getThemeAccent(this);
        FrameLayout drawer = new FrameLayout(this);
        drawer.setBackgroundColor(0xF5101813);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(dp(320), -1);
        lp.gravity = Gravity.START;
        drawer.setLayoutParams(lp);
        ScrollView scroll = new ScrollView(this);
        LinearLayout items = new LinearLayout(this);
        items.setOrientation(LinearLayout.VERTICAL);
        items.setPadding(dp(16), dp(16), dp(16), dp(16));
        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView title = new TextView(this);
        title.setText("FH1 Live Tuning");
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(accent);
        header.addView(title, new LinearLayout.LayoutParams(0, -2, 1.0f));
        header.addView(bindClick(createChipButton("Close", false), "hud_close"), new LinearLayout.LayoutParams(-2, -2));
        items.addView(header);
        hudTempText = new TextView(this);
        hudTempText.setText(String.format(Locale.ROOT, "Battery Temp: %.1f°C", currentBatteryTempC));
        hudTempText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        hudTempText.setTextColor(0xFF93A597);
        hudTempText.setPadding(0, dp(4), 0, dp(10));
        items.addView(hudTempText);
        Button hostBtn = createChipButton("Open Host Settings & Trainer", false);
        GradientDrawable hgd = (GradientDrawable) hostBtn.getBackground();
        if (hgd != null) hgd.setColor(0xDD1B3B2B);
        hostBtn.setTextColor(0xFF5CE68B);
        items.addView(bindClick(hostBtn, "open_host_settings"));
        addHudSectionTitle(items, "Quick Toggles");
        addSwitch(items, "Auto Accelerate", autoThrottle, "toggle_auto_throttle");
        addSwitch(items, "Performance Overlay", showFpsOverlay, "toggle_fps_overlay");
        addSwitch(items, "Menu Mode D-Pad", inMenuMode, "toggle_menu_mode");
        addSwitch(items, "Sun Shadows", prefs.getBoolean("fh1_shadows", true), "toggle_shadows");
        addSwitch(items, "Single-Pass Scene", prefs.getBoolean("fh1_single_pass", true), "toggle_single_pass");
        addSwitch(items, "Bloom Effect", prefs.getBoolean("fh1_bloom", false), "toggle_bloom");
        addSwitch(items, "Experimental Gyro", prefs.getBoolean("experimental_gyro", false), "toggle_gyro");
        addHudRow(items, "Control Scheme", new String[]{"Arrows", "Tilt Gyro", "Classic"}, new String[]{"ctrl_arrows", "ctrl_tilt_a", "ctrl_classic"}, "tilt_a".equals(controlScheme) ? 1 : "classic".equals(controlScheme) ? 2 : 0);
        addSwitch(items, "Treasure Map", prefs.getBoolean("treasure_map", true), "toggle_treasure_map");
        addHudSectionTitle(items, "Live Performance & Graphics");
        addHudRow(items, "Graphics Preset", new String[]{"Quality 30", "Smooth 60", "Ultra"}, new String[]{"preset_quality", "preset_smooth", "preset_ultra"}, -1);
        addHudRow(items, "Target FPS", new String[]{"30 FPS", "45 FPS", "60 FPS", "Max"}, new String[]{"fps_30", "fps_45", "fps_60", "fps_0"}, currentFpsTarget == 0 ? 3 : currentFpsTarget == 60 ? 2 : currentFpsTarget == 45 ? 1 : 0);
        int curBr = prefs.getInt("screen_brightness", 100);
        addHudRow(items, "Brightness", new String[]{"100%", "80%", "60%", "40%"}, new String[]{"br_100", "br_80", "br_60", "br_40"}, curBr <= 40 ? 3 : curBr <= 60 ? 2 : curBr <= 80 ? 1 : 0);
        addHudRow(items, "Reflections", new String[]{"100%", "50%", "25%", "Off"}, new String[]{"ref_100", "ref_50", "ref_25", "ref_0"}, 2);
        addHudRow(items, "Output Upscaler", new String[]{"FSR 1.0", "CAS", "Bilinear"}, new String[]{"up_fsr", "up_cas", "up_bilinear"}, -1);
        String curAsp = prefs.getString(PREF_ASPECT_MODE, "hor_plus");
        addHudRow(items, "Aspect Ratio", new String[]{"Hor+ Ultrawide", "16:9 Fit"}, new String[]{"asp_hor_plus", "asp_16_9"}, "hor_plus".equals(curAsp) ? 0 : 1);
        addSwitch(items, "VSync", prefs.getBoolean("vsync", true), "toggle_vsync");
        int curOp = prefs.getInt("touch_opacity", 100);
        addHudRow(items, "Touch Opacity", new String[]{"100%", "75%", "50%", "Hidden"}, new String[]{"op_100", "op_75", "op_50", "op_0"}, curOp == 0 ? 3 : curOp == 50 ? 2 : curOp == 75 ? 1 : 0);
        addHudRow(items, "Steer Height", new String[]{"Comfort 65%", "High 55%", "72%", "Low 82%"}, new String[]{"sty_65", "sty_55", "sty_72", "sty_82"}, steerYPct == 82 ? 3 : steerYPct == 72 ? 2 : steerYPct == 55 ? 1 : 0);
        addHudRow(items, "Steer Inset", new String[]{"Normal 65dp", "Edge 35dp", "Inset 95dp", "Deep 130dp"}, new String[]{"stx_65", "stx_35", "stx_95", "stx_130"}, steerXDp == 130 ? 3 : steerXDp == 95 ? 2 : steerXDp == 35 ? 1 : 0);
        addSwitch(items, "Steering Horizon", prefs.getBoolean("touch_horizon", true), "toggle_horizon");
        addHudSectionTitle(items, "Controls & Help");
        addToggle(items, "Recalibrate Gyro 0°", true, "gyro_cal");
        addToggle(items, "Touch Controls Guide", false, "touch_guide");
        Button quitBtn = createChipButton("Quit to Launcher", false);
        GradientDrawable qgd = (GradientDrawable) quitBtn.getBackground();
        if (qgd != null) qgd.setColor(0xDD3A1618);
        quitBtn.setTextColor(0xFFFF6B6B);
        items.addView(bindClick(quitBtn, "quit_game"));
        scroll.addView(items);
        drawer.addView(scroll);
        return drawer;
    }

    @Override
    public void onClick(View v) {
        Object tag = v.getTag();
        if (tag == null) return;
        pulseHaptic(3);
        String t = tag.toString();
        toggleQuickHud();
        if ("quit_game".equals(t)) confirmQuit();
        else if ("open_host_settings".equals(t)) {
            try { nativeAction(2, 0.0f); } catch (UnsatisfiedLinkError ignored) {}
        } else if (t.startsWith("br_")) {
            int b = Integer.parseInt(t.substring(3));
            prefs.edit().putInt("screen_brightness", b).apply();
            applyBrightness(b);
            toast("Brightness: " + b + "%");
        } else if ("toggle_auto_throttle".equals(t)) {
            autoThrottle = !autoThrottle;
            prefs.edit().putBoolean("auto_throttle", autoThrottle).apply();
            if (!inMenuMode) currentThrottle = autoThrottle ? 1.0f : 0.0f;
            flushOverrides();
            toast("Auto Throttle: " + (autoThrottle ? "ON" : "OFF"));
        } else if ("toggle_shadows".equals(t)) {
            boolean s = !prefs.getBoolean("fh1_shadows", true);
            prefs.edit().putBoolean("fh1_shadows", s).apply();
            try { nativeAction(8, s ? 1.0f : 0.0f); } catch (UnsatisfiedLinkError ignored) {}
            toast("Shadows: " + (s ? "ON" : "OFF"));
        } else if ("toggle_single_pass".equals(t)) {
            boolean sp = !prefs.getBoolean("fh1_single_pass", true);
            prefs.edit().putBoolean("fh1_single_pass", sp).apply();
            try { nativeAction(9, sp ? 1.0f : 0.0f); } catch (UnsatisfiedLinkError ignored) {}
            toast("Single-Pass: " + (sp ? "ON" : "OFF"));
        } else if ("toggle_bloom".equals(t)) {
            boolean bl = !prefs.getBoolean("fh1_bloom", false);
            prefs.edit().putBoolean("fh1_bloom", bl).apply();
            try { nativeAction(11, bl ? 1.0f : 0.0f); } catch (UnsatisfiedLinkError ignored) {}
            toast("Bloom: " + (bl ? "ON" : "OFF"));
        } else if (t.startsWith("ref_")) {
            float r = Float.parseFloat(t.substring(4)) / 100.0f;
            try { nativeAction(10, r); } catch (UnsatisfiedLinkError ignored) {}
            toast("Reflections: " + t.substring(4) + "%");
        } else if ("toggle_fps_overlay".equals(t)) {
            showFpsOverlay = !showFpsOverlay;
            prefs.edit().putBoolean("fps_overlay", showFpsOverlay).apply();
            if (rr3Overlay != null) rr3Overlay.setShowFpsOverlay(showFpsOverlay);
            toast("FPS Overlay: " + (showFpsOverlay ? "ON" : "OFF"));
        } else if ("toggle_menu_mode".equals(t)) {
            inMenuMode = !inMenuMode;
            if (inMenuMode) currentThrottle = 0.0f;
            else if (autoThrottle) currentThrottle = 1.0f;
            flushOverrides();
            if (rr3Overlay != null) rr3Overlay.postInvalidate();
            toast("Mode: " + (inMenuMode ? "MENU" : "DRIVE"));
        } else if ("toggle_gyro".equals(t)) {
            boolean next = !prefs.getBoolean("experimental_gyro", false);
            prefs.edit().putBoolean("experimental_gyro", next).apply();
            if (sensorManager != null && gameRotationSensor != null) {
                if (next && "tilt_a".equals(controlScheme)) sensorManager.registerListener(sensorListener, gameRotationSensor, SensorManager.SENSOR_DELAY_GAME);
                else sensorManager.unregisterListener(sensorListener);
            }
            toast("Gyro: " + (next ? "ON" : "OFF"));
        } else if (t.startsWith("ctrl_")) {
            String c = t.substring(5);
            controlScheme = c;
            prefs.edit().putString("control_scheme", controlScheme).apply();
            if (sensorManager != null && gameRotationSensor != null) {
                if (isGyroActive()) sensorManager.registerListener(sensorListener, gameRotationSensor, SensorManager.SENSOR_DELAY_GAME);
                else sensorManager.unregisterListener(sensorListener);
            }
            if (rr3Overlay != null) rr3Overlay.postInvalidate();
            toast("Controls: " + ("tilt_a".equals(controlScheme) ? "Tilt Gyro" : "arrows".equals(controlScheme) ? "Arrows" : "Classic"));
        } else if ("toggle_treasure_map".equals(t)) {
            boolean next = !prefs.getBoolean("treasure_map", true);
            prefs.edit().putBoolean("treasure_map", next).apply();
            try { nativeSetCVar("pinyon_shift_dlc_treasure_map", next ? "true" : "false"); } catch (UnsatisfiedLinkError ignored) {}
            toast("Treasure Map: " + (next ? "ON" : "OFF"));
        } else if (t.startsWith("fps_")) {
            int f = Integer.parseInt(t.substring(4));
            setPacedFpsTarget(f, f == 0 ? "Uncapped" : f + " FPS");
        } else if (t.startsWith("preset_")) {
            String p = t.substring(7);
            int pIdx = "quality".equals(p) ? 0 : "smooth".equals(p) ? 1 : 2;
            try { nativeAction(6, (float) pIdx); } catch (UnsatisfiedLinkError ignored) {}
            toast("Preset: " + p.toUpperCase(Locale.ROOT));
        } else if (t.startsWith("up_")) {
            String u = t.substring(3);
            int uIdx = "fsr".equals(u) ? 1 : "cas".equals(u) ? 2 : 0;
            try { nativeAction(5, (float) uIdx); } catch (UnsatisfiedLinkError ignored) {}
            toast("Upscaler: " + u.toUpperCase(Locale.ROOT));
        } else if (t.startsWith("asp_")) {
            boolean hp = "asp_hor_plus".equals(t);
            prefs.edit().putString(PREF_ASPECT_MODE, hp ? "hor_plus" : "letterbox").apply();
            try { nativeAction(4, hp ? 1.0f : 0.0f); } catch (UnsatisfiedLinkError ignored) {}
            toast("Aspect: " + (hp ? "Hor+" : "16:9"));
        } else if ("toggle_vsync".equals(t)) {
            boolean next = !prefs.getBoolean("vsync", true);
            prefs.edit().putBoolean("vsync", next).apply();
            try { nativeAction(7, next ? 1.0f : 0.0f); } catch (UnsatisfiedLinkError ignored) {}
            toast("VSync: " + (next ? "ON" : "OFF"));
        } else if (t.startsWith("op_")) {
            int op = Integer.parseInt(t.substring(3));
            prefs.edit().putInt("touch_opacity", op).apply();
            if (rr3Overlay != null) rr3Overlay.updateTouchOpacity(op / 100.0f);
            toast("Opacity: " + (op == 0 ? "Hidden" : op + "%"));
        } else if (t.startsWith("sty_")) {
            steerYPct = Integer.parseInt(t.substring(4));
            prefs.edit().putInt("steer_y_pct", steerYPct).apply();
            if (rr3Overlay != null) rr3Overlay.postInvalidate();
            toast("Steer Height: " + steerYPct + "%");
        } else if (t.startsWith("stx_")) {
            steerXDp = Integer.parseInt(t.substring(4));
            prefs.edit().putInt("steer_x_dp", steerXDp).apply();
            if (rr3Overlay != null) rr3Overlay.postInvalidate();
            toast("Steer Inset: " + steerXDp + "dp");
        } else if ("toggle_horizon".equals(t)) {
            boolean next = !prefs.getBoolean("touch_horizon", true);
            prefs.edit().putBoolean("touch_horizon", next).apply();
            if (rr3Overlay != null) rr3Overlay.updateShowHorizon(next);
            toast("Horizon: " + (next ? "ON" : "OFF"));
        } else if ("gyro_cal".equals(t)) {
            recalibrateGyro();
        } else if ("touch_guide".equals(t)) {
            showTouchGuide(this);
        } else if ("shutter".equals(t)) {
            SDLActivity.onNativeKeyDown(KeyEvent.KEYCODE_F8);
            SDLActivity.onNativeKeyUp(KeyEvent.KEYCODE_F8);
            pulseHaptic(0);
            toast("Photo captured");
        }
    }

    private void addHudSectionTitle(LinearLayout container, String text) {
        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        tv.setTextColor(Color.rgb(147, 165, 151));
        tv.setPadding(0, dp(10), 0, dp(4));
        container.addView(tv);
    }

    private Button createChipButton(String text, boolean active) {
        Button b = new Button(this);
        b.setText(text);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        b.setTextColor(active ? Color.rgb(10, 15, 12) : Color.rgb(238, 243, 236));
        GradientDrawable gd = new GradientDrawable();
        gd.setColor(active ? getThemeAccent(this) : Color.rgb(22, 33, 26));
        gd.setCornerRadius(dp(8));
        b.setBackground(gd);
        b.setPadding(dp(4), dp(4), dp(4), dp(4));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, dp(4), 0, 0);
        b.setLayoutParams(lp);
        return b;
    }

    private void initThermalPacer() {
        thermalReceiver = new BroadcastReceiver() {
            @Override public void onReceive(Context c, Intent i) {
                readBatteryTemp(i);
                checkThermalPacing();
            }
        };
        readBatteryTemp(registerReceiver(thermalReceiver, new IntentFilter(Intent.ACTION_BATTERY_CHANGED)));
    }

    private void readBatteryTemp(Intent intent) {
        if (intent != null) {
            int raw = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0);
            if (raw > 0) currentBatteryTempC = raw / 10.0f;
        }
        if (currentBatteryTempC <= 0.0f || currentBatteryTempC == 25.0f) {
            try (BufferedReader br = new BufferedReader(new FileReader("/sys/class/power_supply/battery/temp"))) {
                String l = br.readLine();
                if (l != null) {
                    float v = Float.parseFloat(l.trim());
                    currentBatteryTempC = (v > 100.0f) ? (v / 10.0f) : v;
                }
            } catch (Exception ignored) {}
        }
    }

    private void checkThermalPacing() {
        if (!thermalPacerEnabled) return;
        if (currentBatteryTempC >= 44.0f && currentFpsTarget > 30) setPacedFpsTarget(30, "44°C: 30 FPS");
        else if (currentBatteryTempC >= 42.0f && currentFpsTarget > 45) setPacedFpsTarget(45, "42°C: 45 FPS");
        else if (currentBatteryTempC < 39.5f && currentFpsTarget < 60) setPacedFpsTarget(60, "<40°C: 60 FPS");
    }

    private void setPacedFpsTarget(int fps, String msg) {
        currentFpsTarget = fps;
        toast(msg);
        try {
            nativeAction(3, (float) fps);
            nativeSetCVar("host_present_fps_limit", String.valueOf(fps));
            nativeSetCVar("pinyon_shift_fh1_render_fps_limit", String.valueOf(fps));
        } catch (UnsatisfiedLinkError ignored) {}
    }

    private void startPhotoWatcher(final File photosDir) {
        if (!photosDir.exists()) photosDir.mkdirs();
        photoObserver = new FileObserver(photosDir.getAbsolutePath(), FileObserver.CLOSE_WRITE | FileObserver.MOVED_TO) {
            @Override public void onEvent(int event, String path) {
                if (path != null && path.endsWith(".png")) exportToGallery(new File(photosDir, path));
            }
        };
        photoObserver.startWatching();
    }

    private void exportToGallery(final File photo) {
        try {
            ContentValues v = new ContentValues();
            v.put(MediaStore.Images.Media.DISPLAY_NAME, photo.getName());
            v.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
            if (Build.VERSION.SDK_INT >= 29) v.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/ForzaHorizon");
            Uri uri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v);
            if (uri != null) {
                try (InputStream in = new FileInputStream(photo); OutputStream out = getContentResolver().openOutputStream(uri)) {
                    copy(in, out);
                }
                pulseHaptic(0);
                toast("Photo saved");
            }
        } catch (Exception ignored) {}
    }

    private class RR3OverlayView extends View {
        private final Paint horizonPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint vignettePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint pillPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint strokePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private float tiltDeg = 0.0f;
        private float brakeAlpha = 0.0f;
        private static final int MAX_P = 10;
        private final float[] downX = new float[MAX_P];
        private final float[] downY = new float[MAX_P];
        private final long[] downT = new long[MAX_P];
        private final int[] zone = new int[MAX_P];
        private static final int Z_NONE = 0, Z_BRAKE = 1, Z_THROTTLE = 2, Z_CENTER = 3, Z_EBRAKE = 4, Z_STEER_LEFT = 5, Z_STEER_RIGHT = 6;
        private boolean steerLeftHeld = false, steerRightHeld = false;
        public boolean touchSteerActive = false;
        private String statusFlash = null;
        private long statusFlashUntil = 0;
        private boolean showHorizon = true;
        private float touchAlpha = 1.0f;
        private boolean showFps = true;
        private long lastCenterTapTime = 0;

        RR3OverlayView(Context ctx) {
            super(ctx);
            horizonPaint.setColor(0x33FFFFFF);
            horizonPaint.setStrokeWidth(dp(2));
            horizonPaint.setStyle(Paint.Style.STROKE);
            vignettePaint.setStyle(Paint.Style.FILL);
            textPaint.setColor(Color.WHITE);
            textPaint.setTextSize(dp(12));
            textPaint.setTypeface(Typeface.DEFAULT_BOLD);
            pillPaint.setStyle(Paint.Style.FILL);
            strokePaint.setStyle(Paint.Style.STROKE);
            strokePaint.setStrokeWidth(dp(1.5f));
            showHorizon = prefs != null && prefs.getBoolean("touch_horizon", true);
            showFps = prefs != null && prefs.getBoolean("fps_overlay", true);
            touchAlpha = (prefs != null ? prefs.getInt("touch_opacity", 100) : 100) / 100.0f;
        }

        void setTiltAngle(float deg) {
            tiltDeg = deg;
            if (showHorizon) postInvalidate();
        }

        void updateShowHorizon(boolean s) { showHorizon = s; postInvalidate(); }
        void updateTouchOpacity(float o) { touchAlpha = o; postInvalidate(); }
        void setShowFpsOverlay(boolean s) { showFps = s; postInvalidate(); }

        void flashStatus(String s) {
            statusFlash = s;
            statusFlashUntil = System.currentTimeMillis() + 2200;
            postInvalidate();
        }

        private void updateArrowSteer() {
            steerLeftHeld = steerRightHeld = false;
            for (int i = 0; i < MAX_P; i++) {
                if (zone[i] == Z_STEER_LEFT) steerLeftHeld = true;
                if (zone[i] == Z_STEER_RIGHT) steerRightHeld = true;
            }
            touchSteerActive = (steerLeftHeld || steerRightHeld);
            if (steerLeftHeld && !steerRightHeld) currentSteerX = -1.0f;
            else if (steerRightHeld && !steerLeftHeld) currentSteerX = 1.0f;
            else if (!isGyroActive()) currentSteerX = 0.0f;
        }

        private void updatePedals() {
            boolean b = false, t = false;
            for (int i = 0; i < MAX_P; i++) {
                if (zone[i] == Z_BRAKE) b = true;
                if (zone[i] == Z_THROTTLE) t = true;
            }
            currentBrake = b ? 1.0f : 0.0f;
            brakeAlpha = b ? 1.0f : 0.0f;
            if (inMenuMode) {
                currentThrottle = 0.0f;
            } else if (autoThrottle) {
                currentThrottle = b ? 0.0f : 1.0f;
            } else {
                currentThrottle = t ? 1.0f : 0.0f;
            }
        }

        @Override
        protected void onDraw(Canvas c) {
            super.onDraw(c);
            int w = getWidth(), h = getHeight();
            if (w == 0 || h == 0) return;

            if (brakeAlpha > 0.01f) {
                vignettePaint.setColor(Color.argb(Math.round(brakeAlpha * 70), 220, 30, 30));
                c.drawRect(0, 0, w, h, vignettePaint);
            }

            if (showHorizon && "tilt_a".equals(controlScheme)) {
                c.save();
                c.rotate(-tiltDeg, w * 0.5f, h * 0.5f);
                float lineLen = dp(80);
                c.drawLine(w * 0.5f - lineLen, h * 0.5f, w * 0.5f - dp(20), h * 0.5f, horizonPaint);
                c.drawLine(w * 0.5f + dp(20), h * 0.5f, w * 0.5f + lineLen, h * 0.5f, horizonPaint);
                c.drawCircle(w * 0.5f, h * 0.5f, dp(3), horizonPaint);
                c.restore();
            }

            if (touchAlpha > 0.01f && !inMenuMode) {
                int baseAlpha = Math.round(touchAlpha * 255);
                float sY = h * (steerYPct / 100.0f);
                float sMidX = dp(steerXDp + 38);
                pillPaint.setColor(steerLeftHeld ? 0x885CD08A : (0x28000000 | (baseAlpha << 24 & 0xFF000000)));
                c.drawRoundRect(dp(steerXDp), sY - dp(28), sMidX - dp(4), sY + dp(28), dp(12), dp(12), pillPaint);
                pillPaint.setColor(steerRightHeld ? 0x885CD08A : (0x28000000 | (baseAlpha << 24 & 0xFF000000)));
                c.drawRoundRect(sMidX + dp(4), sY - dp(28), dp(steerXDp + 76), sY + dp(28), dp(12), dp(12), pillPaint);

                pillPaint.setColor((currentBrake > 0.1f) ? 0x99E54B4B : 0x30E54B4B);
                c.drawRoundRect(w - dp(90), h * 0.28f, w - dp(24), h * 0.52f, dp(14), dp(14), pillPaint);

                if (!autoThrottle) {
                    pillPaint.setColor((currentThrottle > 0.1f) ? 0x995CD08A : 0x305CD08A);
                    c.drawRoundRect(w - dp(90), h * 0.56f, w - dp(24), h * 0.88f, dp(14), dp(14), pillPaint);
                }

                pillPaint.setColor(0x40000000);
                c.drawCircle(dp(36), dp(60), dp(22), pillPaint);
                c.drawCircle(w - dp(36), dp(60), dp(22), pillPaint);
            }

            if (showFps) {
                textPaint.setColor(0xFFB0FFB0);
                float ft = 16.6f;
                try { ft = nativeGetFrameTimeMs(); } catch (UnsatisfiedLinkError ignored) {}
                float fps = ft > 0.1f ? (1000.0f / ft) : 0.0f;
                c.drawText(String.format(Locale.ROOT, "%.0f FPS (%.1f ms)", fps, ft), dp(20), dp(24), textPaint);
            }

            if (statusFlash != null && System.currentTimeMillis() < statusFlashUntil) {
                textPaint.setColor(Color.WHITE);
                textPaint.setTextAlign(Paint.Align.CENTER);
                c.drawText(statusFlash, w * 0.5f, dp(48), textPaint);
                textPaint.setTextAlign(Paint.Align.LEFT);
            }
        }

        @Override
        public boolean onTouchEvent(MotionEvent event) {
            int action = event.getActionMasked();
            int actionIdx = event.getActionIndex();
            int pointerId = event.getPointerId(actionIdx);
            int w = getWidth(), h = getHeight();

            if (action == MotionEvent.ACTION_DOWN) {
                float px = event.getX(actionIdx), py = event.getY(actionIdx);
                if (py < dp(44) && px > w * 0.35f && px < w * 0.65f) {
                    toggleQuickHud();
                    return true;
                }
            }

            if (inMenuMode) {
                int buttons = 0, pCount = event.getPointerCount();
                for (int i = 0; i < pCount; i++) {
                    if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) continue;
                    if (action == MotionEvent.ACTION_POINTER_UP && i == actionIdx) continue;
                    float px = event.getX(i), py = event.getY(i);
                    float dcx = px - dp(96), dcy = py - (h - dp(96));
                    if (Math.abs(dcx) < dp(80) && Math.abs(dcy) < dp(80)) {
                        if (dcy < -dp(16)) buttons |= BTN_DPAD_UP;
                        else if (dcy > dp(16)) buttons |= BTN_DPAD_DOWN;
                        if (dcx < -dp(16)) buttons |= BTN_DPAD_LEFT;
                        else if (dcx > dp(16)) buttons |= BTN_DPAD_RIGHT;
                    }
                    float dax = px - (w - dp(96)), day = py - (h - dp(96));
                    if (Math.abs(dax) < dp(80) && Math.abs(day) < dp(80)) {
                        if (day > dp(16)) buttons |= BTN_A;
                        if (dax > dp(16)) buttons |= BTN_B;
                        if (dax < -dp(16)) buttons |= BTN_X;
                        if (day < -dp(16)) buttons |= BTN_Y;
                    }
                }
                if ((buttons & ~currentButtons) != 0) pulseHaptic(3);
                currentButtons = buttons;
                currentSteerX = currentSteerY = currentThrottle = currentBrake = currentLookX = currentLookY = 0.0f;
                flushOverrides();
                postInvalidate();
                return true;
            }

            switch (action) {
                case MotionEvent.ACTION_DOWN:
                case MotionEvent.ACTION_POINTER_DOWN: {
                    float x = event.getX(actionIdx), y = event.getY(actionIdx);
                    long now = System.currentTimeMillis();
                    if (pointerId < MAX_P) {
                        downX[pointerId] = x;
                        downY[pointerId] = y;
                        downT[pointerId] = now;
                    }
                    if (Math.hypot(x - dp(36), y - dp(60)) <= dp(22)) {
                        pulseButton(BTN_Y, 200);
                        pulseHaptic(3);
                        toast("Rewind");
                        return true;
                    }
                    if (Math.hypot(x - (w - dp(36)), y - dp(60)) <= dp(22)) {
                        if (pointerId < MAX_P) zone[pointerId] = Z_EBRAKE;
                        currentButtons |= BTN_A;
                        pulseHaptic(3);
                        flushOverrides();
                        postInvalidate();
                        return true;
                    }
                    if (x > w * 0.38f && x < w * 0.62f && y > h - dp(36)) {
                        pulseButton(BTN_X, 150);
                        return true;
                    }
                    int z = Z_NONE;
                    float sY = h * (steerYPct / 100.0f);
                    float sMidX = dp(steerXDp + 38);
                    float sEdge = dp(steerXDp + 115);
                    if (x < sEdge && Math.abs(y - sY) < dp(80)) {
                        z = (x < sMidX) ? Z_STEER_LEFT : Z_STEER_RIGHT;
                        pulseHaptic(3);
                    } else if (x >= w * 0.50f) {
                        z = (y < h * 0.52f) ? Z_BRAKE : Z_THROTTLE;
                        pulseHaptic(3);
                    } else {
                        z = Z_CENTER;
                    }
                    if (pointerId < MAX_P) zone[pointerId] = z;
                    if (z == Z_STEER_LEFT || z == Z_STEER_RIGHT) updateArrowSteer();
                    else if (z == Z_BRAKE || z == Z_THROTTLE) updatePedals();
                    flushOverrides();
                    postInvalidate();
                    return true;
                }
                case MotionEvent.ACTION_MOVE: {
                    for (int i = 0; i < event.getPointerCount(); i++) {
                        int pId = event.getPointerId(i);
                        if (pId < MAX_P) {
                            if (zone[pId] == Z_STEER_LEFT || zone[pId] == Z_STEER_RIGHT) {
                                int nZ = (event.getX(i) < dp(steerXDp + 38)) ? Z_STEER_LEFT : Z_STEER_RIGHT;
                                if (nZ != zone[pId]) {
                                    zone[pId] = nZ;
                                    pulseHaptic(3);
                                    updateArrowSteer();
                                }
                            } else if (zone[pId] == Z_BRAKE || zone[pId] == Z_THROTTLE) {
                                float py = event.getY(i), px = event.getX(i);
                                int nZ = (px >= w * 0.45f) ? ((py < h * 0.52f) ? Z_BRAKE : Z_THROTTLE) : Z_CENTER;
                                if (nZ != zone[pId]) {
                                    zone[pId] = nZ;
                                    pulseHaptic(3);
                                    updatePedals();
                                }
                            } else if (zone[pId] == Z_CENTER && prefs != null && prefs.getBoolean(PREF_LOOK_AROUND, true)) {
                                float dx = event.getX(i) - downX[pId], dy = event.getY(i) - downY[pId];
                                currentLookX = Math.min(1.0f, Math.max(-1.0f, dx / dp(80)));
                                currentLookY = Math.min(1.0f, Math.max(-1.0f, -dy / dp(80)));
                            }
                        }
                    }
                    flushOverrides();
                    return true;
                }
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_POINTER_UP: {
                    int pId = event.getPointerId(actionIdx);
                    int z = pId < MAX_P ? zone[pId] : Z_NONE;
                    float dx = event.getX(actionIdx) - (pId < MAX_P ? downX[pId] : 0);
                    float dy = event.getY(actionIdx) - (pId < MAX_P ? downY[pId] : 0);
                    long dur = System.currentTimeMillis() - (pId < MAX_P ? downT[pId] : 0);
                    if (z == Z_EBRAKE) {
                        currentButtons &= ~BTN_A;
                    } else if (z == Z_STEER_LEFT || z == Z_STEER_RIGHT) {
                        if (pId < MAX_P) zone[pId] = Z_NONE;
                        updateArrowSteer();
                    } else if (z == Z_BRAKE || z == Z_THROTTLE) {
                        if (pId < MAX_P) zone[pId] = Z_NONE;
                        updatePedals();
                    } else if (z == Z_CENTER) {
                        currentLookX = currentLookY = 0.0f;
                        if (dur < 350) {
                            if (dy < -dp(35) && Math.abs(dx) < dp(45)) triggerShift(true);
                            else if (dy > dp(35) && Math.abs(dx) < dp(45)) triggerShift(false);
                            else if (dx < -dp(50) && Math.abs(dy) < dp(45)) pulseButton(BTN_Y, 250);
                            else if (Math.abs(dx) < dp(20) && Math.abs(dy) < dp(20)) {
                                long now = System.currentTimeMillis();
                                if (now - lastCenterTapTime < 320) {
                                    pulseButton(BTN_RIGHT_SHOULDER, 120);
                                    lastCenterTapTime = 0;
                                } else {
                                    lastCenterTapTime = now;
                                }
                            }
                        }
                    }
                    if (pId < MAX_P) zone[pId] = Z_NONE;
                    flushOverrides();
                    postInvalidate();
                    return true;
                }
                case MotionEvent.ACTION_CANCEL: {
                    currentBrake = brakeAlpha = currentLookX = currentLookY = 0.0f;
                    currentThrottle = autoThrottle ? 1.0f : 0.0f;
                    currentButtons = 0;
                    for (int i = 0; i < MAX_P; i++) zone[i] = Z_NONE;
                    updateArrowSteer();
                    updatePedals();
                    flushOverrides();
                    postInvalidate();
                    return true;
                }
            }
            return super.onTouchEvent(event);
        }
    }

    public static void showTouchGuide(Context context) {
        if (context instanceof PinyonShiftActivity) {
            ((PinyonShiftActivity) context).toast("Left: Steer · Right: Brake/Gas · Top: Tuning");
        }
    }

    static int getThemeAccent(Context ctx) {
        return ctx.getSharedPreferences("pinyon_shift_settings", MODE_PRIVATE).getInt("theme_accent", Color.rgb(92, 208, 138));
    }

    private int dp(float value) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, getResources().getDisplayMetrics()));
    }

}
