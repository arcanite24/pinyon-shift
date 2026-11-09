package studio.deimos.pinyonshift;

import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.system.ErrnoException;
import android.system.Os;
import android.util.Log;
import android.view.Display;
import android.view.WindowManager;
import android.widget.Toast;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import org.libsdl.app.SDLActivity;

/**
 * SDL's activity with the game's paths and arguments (AP-1.4, AP-3.3).
 *
 * The game reads its folders from the environment, as tools/pinyon.py sets
 * them on a PC: PINYON_SHIFT_GAME_ROOT holds the files extracted from the
 * player's disc and PINYON_SHIFT_STATE_ROOT the saves, settings, caches, logs
 * and mods. Both live in the app's external files folder, which needs no
 * permission and is reachable over adb and MTP, so a save copies between the
 * device and a PC as a folder. Process environment set here, before SDL
 * starts the native thread, is what the game's getenv sees.
 *
 * Tooling can override any variable with a string extra named env.NAME and
 * pass game arguments as a string-array extra named args:
 *
 *   adb shell am start -n studio.deimos.pinyonshift/.PinyonShiftActivity \
 *       --es env.PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT /sdcard/.../route.fh1test \
 *       --esa args --gpu_backend=null
 */
public class PinyonShiftActivity extends SDLActivity {
    private static final String TAG = "PinyonShift";
    private static final int REQUEST_GPU_DRIVER_ZIP = 0x5053;
    private File driversDir;

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
}
