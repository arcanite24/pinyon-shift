package studio.deimos.pinyonshift;

import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.system.ErrnoException;
import android.system.Os;
import android.util.Log;
import android.view.WindowManager;
import android.widget.Toast;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
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

    // The C++ runtime first, then the ReXGlue runtime, which holds SDL and
    // registers its Java natives when loaded, then the game (libmain.so),
    // whose SDL_main SDL calls.
    @Override
    protected String[] getLibraries() {
        return new String[] {"c++_shared", "rexruntime", "main"};
    }

    @Override
    protected String[] getArguments() {
        Intent intent = getIntent();
        String[] arguments = intent != null ? intent.getStringArrayExtra("args") : null;
        return arguments != null ? arguments : new String[0];
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

    // Adreno 7xx: Mesa Turnip Gen8 V37 (measured on the Adreno 740 against
    // the system driver and newer Turnip builds). Others keep the system's.
    private static String recommendedDriver(String adreno) {
        return adreno.startsWith("7") ? "turnip-gen8-v37" : null;
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
