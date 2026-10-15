package studio.deimos.pinyonshift;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.provider.Settings;
import android.text.InputFilter;
import android.text.InputType;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The app's entry point (ONE_CLICK_SETUP_BACKLOG A-4). With the game files
 * in place it starts the game at once. Without them, or when opened from
 * the "Get files from PC" shortcut, it gets them without adb or developer
 * options: from the PC launcher's Android panel over the local network,
 * found by a UDP broadcast and paired with the six-digit code the panel
 * shows, or from a folder copied to the device over USB, through the
 * system's folder picker.
 *
 * Files go where tools/pinyon.py android push-data puts them: the game in
 * files/game/base, the rest in files/state. A copy that stops resumes where
 * it was. The save is replaced only when chosen here, after a backup.
 *
 * The PC's mods (with its custom radio stations and the XE mod) come as a
 * set: their generated patches were built on the PC for exactly its enabled
 * mods, so the rows are copied together, each mod folder ends up as on the
 * PC (files it no longer has move to state/backups), and enabled_mods is set
 * to the PC's list once the copy is complete.
 *
 * When the share offers a newer build of this app than the one installed,
 * this screen says so and hands it to the system installer.
 */
public class SetupActivity extends Activity implements View.OnClickListener {
    private static final String TAG = "PinyonShiftSetup";
    private static final int HTTP_PORT = 47615;
    private static final int DISCOVERY_PORT = 47616;
    private static final int REQUEST_FOLDER = 0x5055;
    private static final int ACCENT = Color.rgb(241, 174, 54);
    private static final int MUTED = Color.rgb(159, 178, 165);
    // Game files being copied: the game does not start from a partial copy.
    private static final String INCOMPLETE = "game/.copy-incomplete";
    // Arguments the game activity adds at every start (1000 Club offline).
    static final String ARGUMENTS_FILE = "state/config/android-arguments.txt";
    // The app shortcut "Get files from PC" opens this screen with the game installed.
    private static final String SETUP_ACTION = "studio.deimos.pinyonshift.SETUP";
    // The game's settings, where enabled_mods lives.
    static final String CONFIG_FILE = "state/config/pinyon_shift.toml";
    // enabled_mods to set once the game has written its settings file (a mod
    // set copied before the game's first start), applied by the game activity.
    static final String PENDING_MODS_FILE = "state/config/pending-enabled-mods.txt";
    // A mod set being copied, naming its backup folder; and what each mirrored
    // file was on the PC when copied (size and time), to find changed files.
    private static final String MODS_INCOMPLETE = "state/cache/pc-share/mods-incomplete";
    private static final String MODS_INDEX = "state/cache/pc-share/mods-index.json";
    // The system installer's answer for an app update.
    private static final String INSTALL_STATUS = "studio.deimos.pinyonshift.INSTALL_STATUS";

    private File base;
    private TextView intro;
    private TextView discoveryText;
    private EditText addressField;
    private EditText codeField;
    private Button connectButton;
    private LinearLayout groupsBox;
    private TextView spaceText;
    private Button copyButton;
    private ProgressBar progress;
    private TextView progressText;
    private Button folderButton;
    private Button playButton;
    private TextView updateText;
    private Button updateButton;
    private BroadcastReceiver installReceiver;
    private final Map<String, CheckBox> groupChecks = new LinkedHashMap<>();
    private final Map<String, String> groupSets = new HashMap<>();
    private boolean linking;
    private JSONObject manifest;
    private String server;
    private volatile boolean busy;
    private volatile boolean discovering;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        File external = getExternalFilesDir(null);
        base = external != null ? external : getFilesDir();
        Intent intent = getIntent();
        boolean asked = intent != null && (SETUP_ACTION.equals(intent.getAction())
                || intent.getBooleanExtra("setup", false));
        if (gameReady() && !asked) {
            startGame();
            return;
        }
        buildLayout();
        refresh();
        startDiscovery();
        installReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent status) {
                installStatus(status);
            }
        };
        // Sent by the system through this app's own PendingIntent: not exported.
        registerReceiver(installReceiver, new IntentFilter(INSTALL_STATUS), Context.RECEIVER_NOT_EXPORTED);
    }

    @Override
    protected void onDestroy() {
        discovering = false;
        if (installReceiver != null) unregisterReceiver(installReceiver);
        super.onDestroy();
    }

    private boolean gameReady() {
        return new File(base, "game/base/default.xex").isFile() && !new File(base, INCOMPLETE).exists();
    }

    private void startGame() {
        Intent game = new Intent(this, PinyonShiftActivity.class);
        Intent intent = getIntent();
        if (intent != null && intent.getExtras() != null) {
            game.putExtras(intent.getExtras());
            game.removeExtra("setup");
        }
        startActivity(game);
        finish();
    }

    // ---- Layout -------------------------------------------------------

    private int dp(float value) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                getResources().getDisplayMetrics()));
    }

    private TextView text(LinearLayout parent, String value, float size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
        view.setTextColor(color);
        view.setLineSpacing(0, 1.15f);
        if (bold) view.setTypeface(Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(8);
        parent.addView(view, params);
        return view;
    }

    private Button button(LinearLayout parent, String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setOnClickListener(this);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(8);
        parent.addView(button, params);
        return button;
    }

    private EditText field(LinearLayout parent, String hint, int type) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setInputType(type);
        field.setSingleLine(true);
        field.setTextColor(Color.WHITE);
        field.setHintTextColor(MUTED);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                dp(320), LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(4);
        parent.addView(field, params);
        return field;
    }

    private void buildLayout() {
        getWindow().setStatusBarColor(Color.rgb(15, 26, 20));
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.rgb(15, 26, 20));
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(28), dp(24), dp(28), dp(32));
        scroll.addView(column);

        text(column, "Pinyon Shift", 26, Color.WHITE, true);
        intro = text(column, "", 15, MUTED, false);

        text(column, "From your PC over Wi-Fi", 18, ACCENT, true).setPadding(0, dp(16), 0, 0);
        text(column, "On the PC, open the Pinyon Shift launcher, choose Android, then Share on Wi-Fi, "
                + "and keep that panel open. This device and the PC must be on the same network.",
                14, MUTED, false);
        discoveryText = text(column, "Looking for the PC…", 14, Color.WHITE, false);
        addressField = field(column, "PC address, such as 192.168.1.20",
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        codeField = field(column, "Six-digit code from the launcher", InputType.TYPE_CLASS_NUMBER);
        codeField.setFilters(new InputFilter[] {new InputFilter.LengthFilter(6)});
        connectButton = button(column, "Connect");
        updateText = text(column, "", 14, ACCENT, false);
        updateText.setVisibility(View.GONE);
        updateButton = button(column, "Install update");
        updateButton.setVisibility(View.GONE);
        groupsBox = new LinearLayout(this);
        groupsBox.setOrientation(LinearLayout.VERTICAL);
        column.addView(groupsBox);
        spaceText = text(column, "", 13, MUTED, false);
        spaceText.setVisibility(View.GONE);
        copyButton = button(column, "Copy to this device");
        copyButton.setVisibility(View.GONE);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(1000);
        progress.setVisibility(View.GONE);
        LinearLayout.LayoutParams barParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        barParams.topMargin = dp(12);
        column.addView(progress, barParams);
        progressText = text(column, "", 13, Color.WHITE, false);

        text(column, "From a folder", 18, ACCENT, true).setPadding(0, dp(20), 0, 0);
        text(column, "Or copy the extracted game folder (the one holding default.xex, in the install folder's "
                + ".local\\game\\base on the PC) to this device over USB, for example into Download, "
                + "and choose it here. It is copied into the app; you can delete the copy afterwards.",
                14, MUTED, false);
        folderButton = button(column, "Choose folder…");

        playButton = button(column, "Play");
        playButton.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        ((LinearLayout.LayoutParams) playButton.getLayoutParams()).topMargin = dp(24);
        setContentView(scroll);
    }

    @Override
    public void onClick(View view) {
        if (view == connectButton) connect();
        else if (view == copyButton) startCopy();
        else if (view == folderButton) chooseFolder();
        else if (view == playButton) startGame();
        else if (view == updateButton) installUpdate();
    }

    // UI changes from the worker threads.
    private void later(final TextView view, final String text) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                view.setText(text);
            }
        });
    }

    private void refreshLater() {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                refresh();
            }
        });
    }

    private void refresh() {
        boolean ready = gameReady();
        intro.setText(ready
                ? "The game is installed. Copy more from your PC here: title update v4, DLC, Rally data, "
                  + "the PC's mods and radio stations, your PC's save or a fresh copy of the game files."
                : "The game files are not on this device yet. They come from your PC, where the game was "
                  + "built from your own disc. About 8 GB is needed.");
        playButton.setEnabled(ready && !busy);
        connectButton.setEnabled(!busy);
        folderButton.setEnabled(!busy);
        copyButton.setEnabled(!busy);
        updateButton.setEnabled(!busy);
    }

    // ---- Discovery and pairing ------------------------------------------

    private void startDiscovery() {
        discovering = true;
        new Thread(new Runnable() {
            @Override
            public void run() {
                discover();
            }
        }, "PcDiscovery").start();
    }

    private void discover() {
        {
            byte[] request = "PINYON-SHIFT-DISCOVER 1".getBytes(StandardCharsets.US_ASCII);
            try (DatagramSocket socket = new DatagramSocket()) {
                socket.setBroadcast(true);
                socket.setSoTimeout(1500);
                long until = System.currentTimeMillis() + 60_000;
                while (discovering && System.currentTimeMillis() < until) {
                    for (InetAddress target : broadcastAddresses()) {
                        try {
                            socket.send(new DatagramPacket(request, request.length, target, DISCOVERY_PORT));
                        } catch (IOException ignored) {
                            // An interface without broadcast; the others still try.
                        }
                    }
                    try {
                        byte[] buffer = new byte[256];
                        DatagramPacket reply = new DatagramPacket(buffer, buffer.length);
                        socket.receive(reply);
                        String[] parts = new String(buffer, 0, reply.getLength(), StandardCharsets.US_ASCII)
                                .trim().split(" ", 4);
                        if (parts.length >= 3 && parts[0].equals("PINYON-SHIFT-HERE")) {
                            final String address = reply.getAddress().getHostAddress() + ":" + parts[2];
                            final String name = parts.length > 3 ? parts[3] : "the PC";
                            runOnUiThread(new Runnable() {
                                @Override
                                public void run() {
                                    discoveryText.setText("Found " + name + " at " + address
                                            + ". Enter the code the launcher shows.");
                                    if (addressField.getText().length() == 0) addressField.setText(address);
                                    codeField.requestFocus();
                                }
                            });
                            return;
                        }
                    } catch (SocketTimeoutException ignored) {
                        // Asked again below.
                    }
                }
                later(discoveryText, "The PC was not found by itself. Enter the address the launcher shows.");
            } catch (IOException error) {
                Log.w(TAG, "discovery failed", error);
                later(discoveryText, "Enter the address the launcher shows.");
            }
        }
    }

    private static List<InetAddress> broadcastAddresses() {
        List<InetAddress> result = new ArrayList<>();
        try {
            for (NetworkInterface adapter : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!adapter.isUp() || adapter.isLoopback()) continue;
                for (InterfaceAddress address : adapter.getInterfaceAddresses()) {
                    if (address.getBroadcast() != null) result.add(address.getBroadcast());
                }
            }
            result.add(InetAddress.getByName("255.255.255.255"));
        } catch (IOException ignored) {
            // No interfaces readable: nothing to send to.
        }
        return result;
    }

    private void connect() {
        String address = addressField.getText().toString().trim()
                .replaceFirst("^https?://", "").replaceAll("/.*$", "");
        String code = codeField.getText().toString().trim();
        if (address.isEmpty() || code.length() != 6) {
            progressText.setText("Enter the PC's address and the six-digit code.");
            return;
        }
        final String host = address.contains(":") ? address : address + ":" + HTTP_PORT;
        busy = true;
        refresh();
        progressText.setText("Connecting to " + host + "…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                fetchManifest(host, code);
            }
        }, "PcConnect").start();
    }

    private void fetchManifest(final String host, String code) {
        {
            try {
                HttpURLConnection connection = open("http://" + host + "/pinyon/v1/manifest", code, 0);
                int status = connection.getResponseCode();
                if (status == 403) throw new RefusedException(readError(connection));
                if (status != 200) throw new IOException("the PC answered " + status);
                final JSONObject result = new JSONObject(readAll(connection.getInputStream()));
                discovering = false;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        server = host;
                        manifest = result;
                        showGroups();
                        showUpdate();
                        progressText.setText("Connected to " + result.optString("name", host) + ".");
                    }
                });
            } catch (IOException | JSONException error) {
                later(progressText, "Could not connect: " + error.getMessage()
                        + ". Check that the launcher is sharing and both are on the same network.");
            } finally {
                busy = false;
                refreshLater();
            }
        }
    }

    private HttpURLConnection open(String url, String code, long offset) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(8000);
        connection.setReadTimeout(30000);
        connection.setRequestProperty("X-Pinyon-Code", code);
        if (offset > 0) connection.setRequestProperty("Range", "bytes=" + offset + "-");
        return connection;
    }

    private static String readError(HttpURLConnection connection) {
        try (InputStream in = connection.getErrorStream()) {
            return in != null ? readAll(in).trim() : "refused";
        } catch (IOException error) {
            return "refused";
        }
    }

    private static String readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        copy(in, out, null);
        return new String(out.toByteArray(), StandardCharsets.UTF_8);
    }

    private void showGroups() {
        groupsBox.removeAllViews();
        groupChecks.clear();
        groupSets.clear();
        JSONArray groups = manifest.optJSONArray("groups");
        if (groups == null) return;
        boolean ready = gameReady();
        for (int i = 0; i < groups.length(); i++) {
            JSONObject group = groups.optJSONObject(i);
            if (group == null) continue;
            final String id = group.optString("id");
            CheckBox check = new CheckBox(this);
            check.setTextColor(Color.WHITE);
            String label = group.optString("label") + " (" + size(group.optLong("bytes")) + ")";
            if (id.equals("save")) {
                label += ": replaces this device's save; the current one is backed up first";
            }
            String set = group.optString("set", "");
            if (!set.isEmpty()) {
                groupSets.put(id, set);
                label += ": copied together with the other mod rows, as this PC plays them";
            }
            check.setText(label);
            boolean selected = group.optBoolean("selected");
            if (id.equals("game")) {
                // Needed to play; a complete copy is only refreshed on request.
                check.setChecked(!ready);
                check.setEnabled(ready);
            } else {
                check.setChecked(selected);
            }
            check.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
                @Override
                public void onCheckedChanged(CompoundButton view, boolean checked) {
                    // The mod rows' generated patches were built for all of
                    // them: they go, or stay, together.
                    String linked = groupSets.get(id);
                    if (linked != null && !linking) {
                        linking = true;
                        for (Map.Entry<String, CheckBox> entry : groupChecks.entrySet()) {
                            if (linked.equals(groupSets.get(entry.getKey()))) entry.getValue().setChecked(checked);
                        }
                        linking = false;
                    }
                    updateSpace();
                }
            });
            groupsBox.addView(check);
            groupChecks.put(id, check);
        }
        spaceText.setVisibility(View.VISIBLE);
        copyButton.setVisibility(View.VISIBLE);
        updateSpace();
    }

    private long selectedBytes() {
        long total = 0;
        JSONArray groups = manifest.optJSONArray("groups");
        for (int i = 0; groups != null && i < groups.length(); i++) {
            JSONObject group = groups.optJSONObject(i);
            CheckBox check = groupChecks.get(group.optString("id"));
            if (check != null && check.isChecked()) total += group.optLong("bytes");
        }
        return total;
    }

    private void updateSpace() {
        spaceText.setText("Selected: " + size(selectedBytes()) + ". Free on this device: "
                + size(base.getUsableSpace()) + ".");
    }

    private static String size(long bytes) {
        if (bytes >= 1L << 30) return String.format(Locale.ROOT, "%.1f GB", bytes / (double) (1L << 30));
        if (bytes >= 1L << 20) return String.format(Locale.ROOT, "%.0f MB", bytes / (double) (1L << 20));
        return String.format(Locale.ROOT, "%.0f KB", Math.max(1, bytes / 1024.0));
    }

    // ---- Copy over the network --------------------------------------

    private void startCopy() {
        if (manifest == null || server == null) return;
        final String code = codeField.getText().toString().trim();
        final List<String> chosen = new ArrayList<>();
        for (Map.Entry<String, CheckBox> entry : groupChecks.entrySet()) {
            if (entry.getValue().isChecked()) chosen.add(entry.getKey());
        }
        if (chosen.isEmpty()) return;
        busy = true;
        refresh();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        progress.setVisibility(View.VISIBLE);
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    copyFromPc(code, chosen);
                    finish("Done. Press Play.", true);
                } catch (IOException | JSONException error) {
                    Log.e(TAG, "copy failed", error);
                    finish("The copy stopped: " + error.getMessage()
                            + ". Press Copy again to continue where it stopped.", false);
                }
            }
        }, "PcCopy").start();
    }

    // The end of a copy, on a worker thread.
    private void finish(final String message, final boolean success) {
        busy = false;
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                if (success) progress.setProgress(progress.getMax());
                progressText.setText(message);
                refresh();
            }
        });
    }

    private void copyFromPc(String code, List<String> chosen) throws IOException, JSONException {
        List<JSONObject> files = new ArrayList<>();
        long total = 0;
        long needed = 0;
        JSONArray groups = manifest.getJSONArray("groups");
        boolean game = chosen.contains("game");
        boolean titleUpdate = chosen.contains("title_update_v4");
        // The mod folders the chosen mod rows carry, and their files' paths.
        Set<String> mods = new HashSet<>();
        Set<String> mirrored = new HashSet<>();
        JSONObject index = readModIndex();
        for (int i = 0; i < groups.length(); i++) {
            JSONObject group = groups.getJSONObject(i);
            if (!chosen.contains(group.getString("id"))) continue;
            boolean mirror = group.optBoolean("mirror");
            JSONArray names = group.optJSONArray("mods");
            for (int j = 0; names != null && j < names.length(); j++) {
                String name = names.getString(j);
                destination("state/mods/" + name + "/mod.toml");  // a plain folder name
                mods.add(name);
            }
            JSONArray list = group.getJSONArray("files");
            for (int j = 0; j < list.length(); j++) {
                JSONObject file = list.getJSONObject(j);
                File target = destination(file.getString("path"));
                long size = file.getLong("size");
                total += size;
                if (mirror) mirrored.add(file.getString("path"));
                if (!upToDate(file, target, mirror, index)) needed += size;
                files.add(file);
            }
        }
        if (needed > base.getUsableSpace() - (256L << 20)) {
            throw new IOException("not enough free space: " + size(needed) + " needed, "
                    + size(base.getUsableSpace()) + " free");
        }
        if (chosen.contains("save")) backUpSave();
        File incomplete = new File(base, INCOMPLETE);
        if (game) {
            incomplete.getParentFile().mkdirs();
            new FileOutputStream(incomplete).close();
        }
        if (!mods.isEmpty()) beginModSet(mods, mirrored);
        long[] done = {0};
        long started = System.currentTimeMillis();
        int sinceIndexWrite = 0;
        for (int i = 0; i < files.size(); i++) {
            JSONObject file = files.get(i);
            String path = file.getString("path");
            long size = file.getLong("size");
            File target = destination(path);
            boolean mirror = mirrored.contains(path);
            if (!upToDate(file, target, mirror, index)) {
                fetch(code, "/pinyon/v1/file/" + file.getInt("index"), target, size, done, total, i + 1,
                        files.size(), started);
                if (mirror) {
                    index.put(path, file.optLong("modified") + ":" + size);
                    if (++sinceIndexWrite >= 64) {
                        writeModIndex(index);
                        sinceIndexWrite = 0;
                    }
                }
            } else {
                done[0] += size;
            }
        }
        if (game) incomplete.delete();
        if (!mods.isEmpty()) {
            writeModIndex(index);
            finishModSet();
        }
        if (titleUpdate) {
            JSONObject extras = manifest.optJSONObject("extras");
            setClubArguments(extras != null && extras.optBoolean("club"));
        }
    }

    // A file already on the device: the same size, and for a mirrored group
    // also the same PC file as when it was copied.
    private static boolean upToDate(JSONObject file, File target, boolean mirror, JSONObject index)
            throws JSONException {
        long size = file.getLong("size");
        if (target.length() != size) return false;
        if (!mirror) return true;
        return target.isFile() && (file.optLong("modified") + ":" + size).equals(index.optString(file.getString("path")));
    }

    // ---- The PC's mods ------------------------------------------------

    private JSONObject readModIndex() {
        File file = new File(base, MODS_INDEX);
        if (!file.isFile()) return new JSONObject();
        try (InputStream in = new FileInputStream(file)) {
            return new JSONObject(readAll(in));
        } catch (IOException | JSONException error) {
            return new JSONObject();
        }
    }

    private void writeModIndex(JSONObject index) throws IOException {
        writeAtomically(new File(base, MODS_INDEX), index.toString());
    }

    private static void writeAtomically(File file, String text) throws IOException {
        file.getParentFile().mkdirs();
        File temp = new File(file.getPath() + ".tmp");
        try (OutputStream out = new FileOutputStream(temp)) {
            out.write(text.getBytes(StandardCharsets.UTF_8));
        }
        if (file.exists() && !file.delete()) throw new IOException("cannot replace " + file);
        if (!temp.renameTo(file)) throw new IOException("cannot write " + file);
    }

    // Before a mod set is copied: the device's enabled_mods goes into a
    // backup folder and is cleared, so a copy that stops plays unmodded, and
    // files in the PC's mod folders that the PC no longer has move into the
    // backup. A copy that stopped resumes into the same backup.
    private void beginModSet(Set<String> mods, Set<String> mirrored) throws IOException {
        File marker = new File(base, MODS_INCOMPLETE);
        File backup = null;
        if (marker.isFile()) {
            try (InputStream in = new FileInputStream(marker)) {
                String path = readAll(in).trim();
                if (!path.isEmpty()) backup = new File(path);
            }
        }
        if (backup == null) {
            String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(new Date());
            backup = new File(base, "state/backups/before-pc-mods-" + stamp);
            backup.mkdirs();
            String previous = enabledMods();
            writeAtomically(new File(backup, "enabled_mods.txt"), (previous != null ? previous : "") + "\n");
            writeAtomically(marker, backup.getAbsolutePath());
        }
        if (enabledMods() != null) setEnabledMods("");
        File root = new File(base, "state/mods");
        int moved = 0;
        for (String mod : mods) {
            moved += moveStale(new File(root, mod), "state/mods/" + mod, mirrored, new File(backup, "mods/" + mod));
        }
        if (moved > 0) later(progressText, moved + " file(s) the PC no longer has were moved to " + backup);
    }

    private static int moveStale(File directory, String path, Set<String> keep, File backup) throws IOException {
        File[] entries = directory.listFiles();
        if (entries == null) return 0;
        int moved = 0;
        for (File entry : entries) {
            String child = path + "/" + entry.getName();
            if (entry.isDirectory()) {
                moved += moveStale(entry, child, keep, new File(backup, entry.getName()));
                continue;
            }
            // A partial download of a file still listed resumes.
            String listed = child.endsWith(".part") ? child.substring(0, child.length() - 5) : child;
            if (keep.contains(listed)) continue;
            File target = new File(backup, entry.getName());
            target.getParentFile().mkdirs();
            if (!entry.renameTo(target)) throw new IOException("cannot move " + entry + " to the backup");
            moved++;
        }
        return moved;
    }

    // After the whole set is copied: the PC's enabled mods, in its order,
    // that are now on the device.
    private void finishModSet() throws IOException {
        JSONObject extras = manifest.optJSONObject("extras");
        JSONArray order = extras != null ? extras.optJSONArray("mods_enabled") : null;
        List<String> enabled = new ArrayList<>();
        for (int i = 0; order != null && i < order.length(); i++) {
            String name = order.optString(i);
            if (!name.isEmpty() && new File(base, "state/mods/" + name + "/mod.toml").isFile()) enabled.add(name);
        }
        setEnabledMods(String.join(",", enabled));
        new File(base, MODS_INCOMPLETE).delete();
        later(progressText, "Mods enabled: " + (enabled.isEmpty() ? "none" : String.join(", ", enabled)));
    }

    private static final Pattern ENABLED_MODS =
            Pattern.compile("^enabled_mods[ \\t]*=[ \\t]*\"([^\"]*)\"[ \\t]*$", Pattern.MULTILINE);

    // enabled_mods in the game's settings, or null without the file.
    private String enabledMods() throws IOException {
        File config = new File(base, CONFIG_FILE);
        if (!config.isFile()) return null;
        try (InputStream in = new FileInputStream(config)) {
            Matcher match = ENABLED_MODS.matcher(readAll(in));
            return match.find() ? match.group(1) : "";
        }
    }

    // Sets enabled_mods in the game's settings file. Before the game's first
    // start there is none, and writing one would skip the defaults the game
    // writes: the list waits in PENDING_MODS_FILE for the game activity.
    private void setEnabledMods(String mods) throws IOException {
        File config = new File(base, CONFIG_FILE);
        File pending = new File(base, PENDING_MODS_FILE);
        if (!config.isFile()) {
            writeAtomically(pending, mods + "\n");
            return;
        }
        pending.delete();
        applyEnabledMods(config, mods);
    }

    // Also called by the game activity for a pending list.
    static void applyEnabledMods(File config, String mods) throws IOException {
        String text;
        try (InputStream in = new FileInputStream(config)) {
            text = readAll(in);
        }
        String line = "enabled_mods = \"" + mods + "\"";
        Matcher match = ENABLED_MODS.matcher(text);
        if (match.find()) {
            text = text.substring(0, match.start()) + line + text.substring(match.end());
        } else if (!mods.isEmpty()) {
            text = text.replaceAll("\n+$", "") + (text.isEmpty() ? "" : "\n") + line + "\n";
        } else {
            return;
        }
        writeAtomically(config, text);
    }

    // ---- App update -----------------------------------------------------

    // The package the PC offers, when it is a newer build of this app.
    private void showUpdate() {
        updateText.setVisibility(View.GONE);
        updateButton.setVisibility(View.GONE);
        JSONObject apk = manifest.optJSONObject("apk");
        if (apk == null) return;
        long offeredCode = apk.optLong("version_code");
        long installedCode;
        String installedVersion;
        try {
            PackageInfo info = getPackageManager().getPackageInfo(getPackageName(),
                    PackageManager.PackageInfoFlags.of(0));
            installedCode = info.getLongVersionCode();
            installedVersion = info.versionName;
        } catch (PackageManager.NameNotFoundException error) {
            return;
        }
        String installedCreated = "";
        try (InputStream in = getAssets().open("pinyon_shift_build.json")) {
            JSONObject own = new JSONObject(readAll(in));
            installedCreated = own.optString("created_utc");
        } catch (IOException | JSONException error) {
            Log.w(TAG, "no build manifest in the package", error);
        }
        // A lower version code cannot install over this one. Packages of one
        // version compare by when they were packaged (ISO 8601 in UTC from
        // pinyon_android.py), so a rebuild with only app changes counts too.
        String offeredCreated = apk.optString("created_utc");
        boolean newer = offeredCode > installedCode
                || (offeredCode == installedCode && !offeredCreated.isEmpty()
                    && offeredCreated.compareTo(installedCreated) > 0);
        if (!newer) return;
        JSONObject extras = manifest.optJSONObject("extras");
        boolean offeredV4 = extras != null && extras.optBoolean("title_update_v4");
        boolean deviceV4 = new File(base, "state/title-update-v4/default.xexp").isFile();
        String what = "The PC has a newer build of Pinyon Shift (" + apk.optString("version") + ", built "
                + apk.optString("created_utc").replaceFirst("\\..*$", "").replace('T', ' ')
                + " UTC; this device has " + installedVersion + "). ";
        if (deviceV4 && !offeredV4) {
            // A v4 save cannot be loaded by the base game again.
            updateText.setText(what + "It is the base game, and this device plays title update v4, whose save "
                    + "the base game cannot load: build the v4 package on the PC to update.");
            updateText.setVisibility(View.VISIBLE);
            return;
        }
        updateText.setText(what + (offeredV4 && !deviceV4
                ? "It plays title update v4: copy the title update v4 row too. A save played on v4 cannot go "
                  + "back to the base game."
                : "Your save and settings stay as they are."));
        updateText.setVisibility(View.VISIBLE);
        updateButton.setVisibility(View.VISIBLE);
    }

    private void installUpdate() {
        if (manifest == null || server == null) return;
        if (!getPackageManager().canRequestPackageInstalls()) {
            // Android asks once whether this app may install apps.
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + getPackageName())));
            } catch (Exception error) {
                Log.w(TAG, "no install permission screen", error);
            }
            progressText.setText("Allow Pinyon Shift to install apps, come back, and press Install update again.");
            return;
        }
        final JSONObject apk = manifest.optJSONObject("apk");
        if (apk == null) return;
        final String code = codeField.getText().toString().trim();
        busy = true;
        refresh();
        progress.setVisibility(View.VISIBLE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    // Named by the package, so a copy of another one never resumes.
                    String build = (apk.optString("created_utc") + apk.optString("build"))
                            .replaceAll("[^0-9A-Fa-f]", "");
                    File file = new File(getCacheDir(), "pinyon-shift-update-"
                            + build.substring(0, Math.min(32, build.length())) + ".apk");
                    File[] old = getCacheDir().listFiles();
                    for (int i = 0; old != null && i < old.length; i++) {
                        String name = old[i].getName();
                        if (name.startsWith("pinyon-shift-update-") && !name.startsWith(file.getName())) {
                            old[i].delete();
                        }
                    }
                    long size = apk.optLong("bytes");
                    if (file.length() != size) {
                        fetch(code, "/pinyon/v1/apk", file, size, new long[] {0}, size, 1, 1,
                                System.currentTimeMillis());
                    }
                    commitUpdate(file);
                    finish("The installer asks to confirm the update. The app closes while it updates; "
                            + "open it again afterwards.", true);
                } catch (IOException error) {
                    Log.e(TAG, "update failed", error);
                    finish("The update stopped: " + error.getMessage() + ". Press Install update to try again.",
                            false);
                }
            }
        }, "AppUpdate").start();
    }

    // The package into a system installer session; the system asks the
    // player to confirm, through INSTALL_STATUS.
    private void commitUpdate(File file) throws IOException {
        PackageInstaller installer = getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params =
                new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(getPackageName());
        params.setSize(file.length());
        int id = installer.createSession(params);
        try (PackageInstaller.Session session = installer.openSession(id)) {
            try (InputStream in = new FileInputStream(file);
                 OutputStream out = session.openWrite("pinyon-shift.apk", 0, file.length())) {
                copy(in, out, null);
                session.fsync(out);
            }
            Intent status = new Intent(INSTALL_STATUS).setPackage(getPackageName());
            // Mutable: the installer adds the result to it.
            PendingIntent callback = PendingIntent.getBroadcast(this, id, status,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_MUTABLE);
            session.commit(callback.getIntentSender());
        } catch (IOException | RuntimeException error) {
            installer.abandonSession(id);
            throw error instanceof IOException ? (IOException) error : new IOException(error.getMessage());
        }
        file.delete();
    }

    private void installStatus(Intent status) {
        int result = status.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (result == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirm = status.getParcelableExtra(Intent.EXTRA_INTENT, Intent.class);
            if (confirm != null) {
                try {
                    startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                } catch (Exception error) {
                    progressText.setText("The system installer did not open: " + error.getMessage());
                }
            }
            return;
        }
        if (result == PackageInstaller.STATUS_SUCCESS) {
            progressText.setText("Updated. Open Pinyon Shift again.");
            return;
        }
        String message = status.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
        progressText.setText(result == PackageInstaller.STATUS_FAILURE_ABORTED
                ? "The update was cancelled."
                : "The update was not installed" + (message != null ? ": " + message : "") + ".");
    }

    // A path from the manifest, inside the app's folder: the game or the state.
    private File destination(String path) throws IOException {
        if (!(path.startsWith("game/base/") || path.startsWith("state/")) || path.contains("\\")) {
            throw new IOException("unexpected path " + path);
        }
        for (String part : path.split("/")) {
            if (part.isEmpty() || part.equals(".") || part.equals("..")) {
                throw new IOException("unexpected path " + path);
            }
        }
        File target = new File(base, path);
        if (!target.getCanonicalPath().startsWith(base.getCanonicalPath() + File.separator)) {
            throw new IOException("unexpected path " + path);
        }
        return target;
    }

    // One file into <name>.part, resumed from its length, then renamed. A
    // dropped connection is retried a few times.
    private void fetch(String code, String resource, File target, long size, final long[] done, final long total,
                       final int number, final int count, final long started) throws IOException {
        File part = new File(target.getPath() + ".part");
        target.getParentFile().mkdirs();
        final long before = done[0];
        IOException last = null;
        for (int attempt = 0; attempt < 6; attempt++) {
            if (attempt > 0) {
                try {
                    Thread.sleep(2000L * attempt);
                } catch (InterruptedException interrupted) {
                    throw new IOException("interrupted");
                }
            }
            long offset = part.length();
            if (offset > size) {
                part.delete();
                offset = 0;
            }
            try {
                HttpURLConnection connection = open("http://" + server + resource, code,
                        offset);
                int status = connection.getResponseCode();
                if (status == 403) throw new RefusedException(readError(connection));
                if (status != 200 && status != 206) throw new IOException("the PC answered " + status);
                boolean append = status == 206;
                if (!append) offset = 0;
                final long startOffset = offset;
                try (InputStream in = connection.getInputStream();
                     OutputStream out = new FileOutputStream(part, append)) {
                    copy(in, out, new Progress() {
                        @Override
                        public void written(long bytes) {
                            done[0] = before + startOffset + bytes;
                            report(done[0], total, number, count, started);
                        }
                    });
                }
                if (part.length() != size) throw new IOException("incomplete download");
                if (target.exists() && !target.delete()) throw new IOException("cannot replace " + target);
                if (!part.renameTo(target)) throw new IOException("cannot write " + target);
                done[0] = before + size;
                return;
            } catch (RefusedException refused) {
                throw refused;
            } catch (IOException error) {
                last = error;
                Log.w(TAG, "retrying " + target, error);
            }
        }
        throw last;
    }

    private long lastReport;

    private void report(long done, long total, int number, int count, long started) {
        long now = System.currentTimeMillis();
        if (now - lastReport < 250) return;
        lastReport = now;
        double seconds = Math.max(1, (now - started) / 1000.0);
        final String line = size(done) + " of " + size(total) + " · file " + number + " of " + count
                + " · " + size((long) (done / seconds)) + "/s";
        final int value = total > 0 ? (int) (done * 1000 / total) : 0;
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                progress.setProgress(value);
                progressText.setText(line);
            }
        });
    }

    // The device's save (everything in state/user but the DLC content),
    // copied to state/backups before the PC's replaces it.
    private void backUpSave() throws IOException {
        File user = new File(base, "state/user");
        File[] entries = user.listFiles();
        if (entries == null || entries.length == 0) return;
        String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(new Date());
        final File backup = new File(base, "state/backups/before-pc-save-" + stamp + "/user");
        for (File entry : entries) {
            if (entry.getName().equals("0000000000000000")) continue;
            copyTree(entry, new File(backup, entry.getName()));
        }
        later(progressText, "This device's save was backed up to " + backup.getParent());
    }

    private static void copyTree(File source, File target) throws IOException {
        if (source.isDirectory()) {
            target.mkdirs();
            File[] children = source.listFiles();
            if (children == null) return;
            for (File child : children) copyTree(child, new File(target, child.getName()));
            return;
        }
        target.getParentFile().mkdirs();
        try (InputStream in = new FileInputStream(source); OutputStream out = new FileOutputStream(target)) {
            copy(in, out, null);
        }
    }

    // 1000 Club offline with title update v4, as the PC launcher sets it.
    private void setClubArguments(boolean club) throws IOException {
        File file = new File(base, ARGUMENTS_FILE);
        file.getParentFile().mkdirs();
        String[] flags = {"--pinyon_shift_car_challenge_gate_probe=true", "--xam_report_live_signin=true"};
        List<String> lines = new ArrayList<>();
        if (file.isFile()) {
            try (InputStream in = new FileInputStream(file)) {
                for (String line : readAll(in).split("\n")) {
                    String trimmed = line.trim();
                    if (trimmed.isEmpty()) continue;
                    boolean flag = false;
                    for (String known : flags) flag |= trimmed.equals(known);
                    if (!flag) lines.add(trimmed);
                }
            }
        }
        if (club) Collections.addAll(lines, flags);
        try (OutputStream out = new FileOutputStream(file)) {
            out.write((String.join("\n", lines) + "\n").getBytes(StandardCharsets.UTF_8));
        }
    }

    // The PC refused the request (a wrong code, or sharing locked): not retried.
    private static final class RefusedException extends IOException {
        RefusedException(String message) {
            super(message);
        }
    }

    interface Progress {
        void written(long bytes);
    }

    private static void copy(InputStream in, OutputStream out, Progress progress) throws IOException {
        byte[] buffer = new byte[1 << 17];
        long written = 0;
        for (int read; (read = in.read(buffer)) > 0; ) {
            out.write(buffer, 0, read);
            written += read;
            if (progress != null) progress.written(written);
        }
    }

    // ---- Copy from a folder -----------------------------------------

    private void chooseFolder() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        try {
            startActivityForResult(intent, REQUEST_FOLDER);
        } catch (Exception error) {
            progressText.setText("This device has no folder picker.");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_FOLDER || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        final Uri tree = data.getData();
        busy = true;
        refresh();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        progress.setVisibility(View.VISIBLE);
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    importFolder(tree);
                    finish("Done. Press Play.", true);
                } catch (IOException error) {
                    Log.e(TAG, "folder import failed", error);
                    finish("The copy stopped: " + error.getMessage() + ". Choose the folder again to continue.",
                            false);
                }
            }
        }, "FolderImport").start();
    }

    private static final class Entry {
        final Uri uri;
        final String path;
        final long size;

        Entry(Uri uri, String path, long size) {
            this.uri = uri;
            this.path = path;
            this.size = size;
        }
    }

    private void importFolder(Uri tree) throws IOException {
        String root = DocumentsContract.getTreeDocumentId(tree);
        List<Entry> files = new ArrayList<>();
        list(tree, root, "", files);
        boolean game = false;
        long total = 0;
        for (Entry entry : files) {
            game |= entry.path.equals("default.xex");
            total += entry.size;
        }
        if (!game) {
            throw new IOException("that folder holds no default.xex; choose the extracted game folder itself");
        }
        if (total > base.getUsableSpace() - (256L << 20)) {
            throw new IOException("not enough free space: " + size(total) + " needed");
        }
        File incomplete = new File(base, INCOMPLETE);
        incomplete.getParentFile().mkdirs();
        new FileOutputStream(incomplete).close();
        long done = 0;
        final long started = System.currentTimeMillis();
        final int count = files.size();
        for (int i = 0; i < files.size(); i++) {
            Entry entry = files.get(i);
            File target = destination("game/base/" + entry.path);
            if (target.length() != entry.size) {
                File part = new File(target.getPath() + ".part");
                target.getParentFile().mkdirs();
                final long before = done;
                final int number = i + 1;
                final long sum = total;
                try (InputStream in = getContentResolver().openInputStream(entry.uri);
                     OutputStream out = new FileOutputStream(part)) {
                    if (in == null) throw new IOException("cannot read " + entry.path);
                    copy(in, out, new Progress() {
                        @Override
                        public void written(long bytes) {
                            report(before + bytes, sum, number, count, started);
                        }
                    });
                }
                if (part.length() != entry.size) throw new IOException("incomplete copy of " + entry.path);
                if (target.exists() && !target.delete()) throw new IOException("cannot replace " + target);
                if (!part.renameTo(target)) throw new IOException("cannot write " + target);
            }
            done += entry.size;
        }
        incomplete.delete();
    }

    private void list(Uri tree, String document, String prefix, List<Entry> out) throws IOException {
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, document);
        try (Cursor cursor = getContentResolver().query(children, new String[] {
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE,
                DocumentsContract.Document.COLUMN_SIZE}, null, null, null)) {
            if (cursor == null) throw new IOException("cannot list the folder");
            while (cursor.moveToNext()) {
                String id = cursor.getString(0);
                String name = cursor.getString(1);
                if (name == null || name.isEmpty() || name.equals(".") || name.equals("..")
                        || name.contains("/")) {
                    continue;
                }
                if (DocumentsContract.Document.MIME_TYPE_DIR.equals(cursor.getString(2))) {
                    list(tree, id, prefix + name + "/", out);
                } else {
                    out.add(new Entry(DocumentsContract.buildDocumentUriUsingTree(tree, id), prefix + name,
                            cursor.getLong(3)));
                }
            }
        }
    }
}
