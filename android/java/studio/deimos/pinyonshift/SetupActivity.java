package studio.deimos.pinyonshift;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.IntentFilter;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.provider.Settings;
import android.util.Log;
import java.text.SimpleDateFormat;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import android.app.*;
import android.content.*;
import android.content.res.ColorStateList;
import android.database.Cursor;
import android.graphics.*;
import android.graphics.drawable.*;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.text.InputFilter;
import android.text.InputType;
import android.util.TypedValue;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
public class SetupActivity extends Activity implements View.OnClickListener, CompoundButton.OnCheckedChangeListener {
  private static final int HTTP_PORT = 47615, DISCOVERY_PORT = 47616, REQUEST_FOLDER = 0x5055, REQUEST_DRIVER_ZIP = 0x5056;
  private static final int COLOR_BG = 0xFF0F1210, COLOR_SURFACE = 0xFF141916, COLOR_CARD = 0xFF181D1A;
  private static final int COLOR_CARD_STROKE = 0xFF26302A, COLOR_HERO_STROKE = 0xFF2F4F3A, COLOR_ACCENT_DEFAULT = 0xFF5CE68B;
  private static final int COLOR_FOG = 0xFFEEF3EC, COLOR_MUTED = 0xFF86968B, COLOR_TEXT_DIM = 0xFF5D6B63, COLOR_SUCCESS = 0xFF5CE68B, COLOR_RED = 0xFFFF6B6B;
  private static final int MP = -1, WC = -2;
  private static final String INCOMPLETE = "game/.copy-incomplete", CONFIG_TOML = "state/config/pinyon-shift.toml", SETUP_ACTION = "studio.deimos.pinyonshift.SETUP";
  static final String ARGUMENTS_FILE = "state/config/android-arguments.txt";
  private static final String TAG = "PinyonShift";
  static final String CONFIG_FILE = "state/config/pinyon_shift.toml";
  static final String PENDING_MODS_FILE = "state/config/pending-enabled-mods.txt";
  private static final String MODS_INCOMPLETE = "state/cache/pc-share/mods-incomplete";
  private static final String MODS_INDEX = "state/cache/pc-share/mods-index.json";
  private static final String INSTALL_STATUS = "studio.deimos.pinyonshift.INSTALL_STATUS";
  private static final String VERTEX_STORES_FALLBACK =
          "--vulkan_require_vertex_pipeline_stores_and_atomics=false";

  private File base, driversDir;
  private SharedPreferences prefs;
  private int colorAccent, currentTab, sysAccent;
  private FrameLayout tabContentContainer;
  private final List<View> tabPages = new ArrayList<>();
  private final List<LinearLayout> navItems = new ArrayList<>();
  private TextView gameTitleText, gameStatusText, activeDriverText, folderPathText, discoveryText, progressText, saveStatusText;
  private TextView aspectModeSummary, resScaleSummary, fpsCapSummary, brightnessSummary, presetSummary, upscalerSummary, controlSummary, themeSummary, touchOpacitySummary, steerHeightSummary, steerInsetSummary;
  private LinearLayout statusPill, launchButton, driverListContainer, backupListContainer, activeBadgesLayout, groupsBox;
  private View statusDot;
  private ImageView launchIcon;
  private TextView launchText;
  private EditText addressField, codeField;
  private Button copyButton;
  private ProgressBar progress;
  private final Map<String, CheckBox> groupChecks = new LinkedHashMap<>();
  private TextView updateText;
  private Button updateButton;
  private BroadcastReceiver installReceiver;
  private final Map<String, String> groupSets = new HashMap<>();
  private boolean linking;

  private JSONObject manifest;
  private String server;
  private volatile boolean busy, discovering;
  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    File external = getExternalFilesDir(null);
    base = external != null ? external : getFilesDir();
    driversDir = new File(base, "state/drivers");
    driversDir.mkdirs();
    prefs = getSharedPreferences("pinyon_shift_settings", MODE_PRIVATE);
    sysAccent = COLOR_ACCENT_DEFAULT;
    if (Build.VERSION.SDK_INT >= 31) {
      try { sysAccent = getResources().getColor(android.R.color.system_accent1_500, getTheme()); } catch (Throwable ignored) {}
    }
    colorAccent = prefs.getInt("theme_accent", sysAccent);
    boolean fromShortcut = SETUP_ACTION.equals(getIntent().getAction());
    if (!fromShortcut && prefs.getBoolean("auto_launch", false) && gameReady()) {
      startGame();
      return;
    }
        installReceiver = new BroadcastReceiver() {
      @Override
      public void onReceive(Context context, Intent status) {
        installStatus(status);
      }
    };
    registerReceiver(installReceiver, new IntentFilter(INSTALL_STATUS), Context.RECEIVER_NOT_EXPORTED);
    buildMaterial3Layout();
    int savedTab = prefs.getInt("active_tab", 0);
    if (savedTab >= 0 && savedTab < tabPages.size()) switchTab(savedTab);
    refreshAllTabs();
  }
  @Override
  protected void onDestroy() {
    super.onDestroy();
    discovering = false;
    if (installReceiver != null) unregisterReceiver(installReceiver);
  }
  private boolean gameReady() {
    return new File(base, "game/base/default.xex").isFile() && !new File(base, INCOMPLETE).exists();
  }
  private void startGame() {
    if (gameReady()) {
      applySettings();
      Intent intent = new Intent(this, PinyonShiftActivity.class);
      intent.putExtra("pinyon_shift_base", base.getAbsolutePath());
      startActivity(intent);
      finish();
    }
  }
  private int dp(float v) { return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics())); }
  private LinearLayout.LayoutParams lp(int w, int h) { return new LinearLayout.LayoutParams(w, h); }
  private LinearLayout.LayoutParams lpWeight1() { return new LinearLayout.LayoutParams(0, WC, 1.0f); }
  private GradientDrawable cardBg(int c, float r) { return cardBg(c, r, 0, 0); }
  private GradientDrawable cardBg(int c, float r, int sc, int s) {
    GradientDrawable d = new GradientDrawable(); d.setColor(c); d.setCornerRadius(dp(r));
    if (s > 0) d.setStroke(dp(s), sc);
    return d;
  }
  private RippleDrawable ripple(int n, int r, float rad) {
    GradientDrawable m = new GradientDrawable(); m.setColor(Color.WHITE); m.setCornerRadius(dp(rad));
    return new RippleDrawable(ColorStateList.valueOf(r), cardBg(n, rad), m);
  }
  private LinearLayout createCard(LinearLayout parent, int p) {
    LinearLayout c = new LinearLayout(this); c.setOrientation(LinearLayout.VERTICAL); c.setBackground(cardBg(COLOR_CARD, 20, COLOR_CARD_STROKE, 1));
    int pad = dp(p); c.setPadding(pad, pad, pad, pad);
    LinearLayout.LayoutParams l = lp(MP, WC); l.bottomMargin = dp(12); c.setLayoutParams(l);
    if (parent != null) parent.addView(c);
    return c;
  }
  private LinearLayout addSection(LinearLayout c, String t) {
    LinearLayout card = createCard(c, 16); card.addView(label(t, 14, Color.WHITE, true)); return card;
  }
  private TextView label(String t, float sp, int c, boolean b) {
    TextView tv = new TextView(this); tv.setText(t); tv.setTextSize(sp); tv.setTextColor(c);
    if (b) tv.setTypeface(Typeface.DEFAULT_BOLD);
    return tv;
  }
  private EditText createField(String hint, int inputType) {
    EditText et = new EditText(this); et.setHint(hint); et.setHintTextColor(COLOR_TEXT_DIM); et.setTextColor(Color.WHITE); et.setTextSize(13); et.setInputType(inputType); et.setBackground(cardBg(COLOR_SURFACE, 8, COLOR_CARD_STROKE, 1)); et.setPadding(dp(12), dp(8), dp(12), dp(8));
    return et;
  }
  private void toast(final String msg) {
    runOnUiThread(new Runnable() { @Override public void run() { Toast.makeText(SetupActivity.this, msg, Toast.LENGTH_SHORT).show(); } });
  }
  private Dialog createCardDialog(String title, LinearLayout c) {
    Dialog d = new Dialog(this); d.requestWindowFeature(Window.FEATURE_NO_TITLE);
    if (d.getWindow() != null) d.getWindow().setBackgroundDrawable(new ColorDrawable(0)); c.setOrientation(LinearLayout.VERTICAL); c.setPadding(dp(18), dp(18), dp(18), dp(14)); c.setBackground(cardBg(0xFF181D1A, 20, 0xFF26302A, 1));
    if (title != null) { TextView tv = label(title, 16, Color.WHITE, true); tv.setPadding(0, 0, 0, dp(10)); c.addView(tv); }
    d.setContentView(c); return d;
  }
  private void confirmDialog(String t, String m, String p, final DialogInterface.OnClickListener ok) {
    LinearLayout c = new LinearLayout(this); final Dialog d = createCardDialog(t, c);
    TextView msg = label(m, 13, COLOR_MUTED, false); msg.setPadding(0, dp(4), 0, dp(12)); c.addView(msg);
    LinearLayout row = new LinearLayout(this);
    Button cancel = createM3Button("Cancel", false); cancel.setLayoutParams(lpWeight1()); cancel.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { d.dismiss(); } }); row.addView(cancel);
    View sp = new View(this); sp.setLayoutParams(lp(dp(10), dp(1))); row.addView(sp);
    Button pos = createM3Button(p, true); pos.setLayoutParams(lpWeight1()); pos.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { d.dismiss(); ok.onClick(d, DialogInterface.BUTTON_POSITIVE); } }); row.addView(pos); c.addView(row); d.show();
  }
  Drawable getSymbol(String name) {
    int id = getResources().getIdentifier(name, "drawable", getPackageName());
    if (id == 0) return null;
    Drawable d = getDrawable(id);
    return d != null ? d.mutate() : null;
  }
  void setButtonIcon(Button b, String name, int tint) {
    Drawable d = getSymbol(name);
    if (d != null) {
      d.setBounds(0, 0, dp(18), dp(18));
      d.setTint(tint);
    }
    if (b != null) {
      b.setCompoundDrawables(d, null, null, null); b.setCompoundDrawablePadding(dp(8));
    }
  }
  private Button createM3Button(String text, boolean primary) {
    return createM3Button(text, null, primary);
  }
  private Button createM3Button(String text, String icon, boolean primary) {
    Button btn = new Button(this);
    btn.setText(text);
    btn.setAllCaps(false); btn.setTextSize(14); btn.setTypeface(Typeface.DEFAULT_BOLD);
    int bg = primary ? colorAccent : COLOR_SURFACE;
    int fg = primary ? 0xFF0B1F11 : colorAccent; btn.setTextColor(fg); btn.setLetterSpacing(0.04f); btn.setBackground(ripple(bg, Color.argb(60, 255, 255, 255), 14)); btn.setPadding(dp(16), dp(10), dp(16), dp(10));
    if (icon != null) setButtonIcon(btn, icon, fg);
    return btn;
  }
  private void buildMaterial3Layout() {
    LinearLayout root = new LinearLayout(this);
    root.setFitsSystemWindows(true); root.setOrientation(LinearLayout.VERTICAL);
    root.setBackgroundColor(COLOR_BG); root.setLayoutParams(lp(MP, MP));
    LinearLayout header = new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL);
    header.setBackgroundColor(Color.TRANSPARENT); header.setPadding(dp(20), dp(14), dp(20), dp(8));
    ImageView mark = new ImageView(this);
    Drawable mk = getSymbol("ic_launcher_foreground");
    if (mk != null) mark.setImageDrawable(mk);
    LinearLayout.LayoutParams mlp = lp(dp(28), dp(28));
    mlp.rightMargin = dp(10); header.addView(mark, mlp);
    TextView title = label("PINYON SHIFT", 20, Color.WHITE, true); title.setTypeface(Typeface.create(Typeface.DEFAULT, Typeface.BOLD_ITALIC)); title.setLetterSpacing(0.08f); header.addView(title, lpWeight1());
    TextView verBadge = label("v0.6.0", 11, COLOR_MUTED, true); verBadge.setBackground(cardBg(0xFF1A241D, 10, COLOR_CARD_STROKE, 1)); verBadge.setPadding(dp(8), dp(3), dp(8), dp(3)); header.addView(verBadge); root.addView(header);
    tabContentContainer = new FrameLayout(this);
    LinearLayout.LayoutParams clp = lp(MP, 0);
    clp.weight = 1.0f; tabContentContainer.setLayoutParams(clp);
    tabPages.clear();
    tabPages.add(buildPlayTab());
    tabPages.add(buildDriversTab());
    tabPages.add(buildSettingsTab());
    tabPages.add(buildContentTab());
    for (int i = 0; i < tabPages.size(); i++) {
      View page = tabPages.get(i);
      page.setVisibility(i == currentTab ? View.VISIBLE : View.GONE); tabContentContainer.addView(page);
    }
    root.addView(tabContentContainer); root.addView(buildBottomNavBar());
    setContentView(root);
  }
  private ScrollView wrapScrollable(View content) {
    ScrollView scroll = new ScrollView(this);
    scroll.setFillViewport(true); scroll.setLayoutParams(new FrameLayout.LayoutParams(MP, MP));
    int p = dp(16); content.setPadding(p, p, p, p); scroll.addView(content);
    return scroll;
  }
  private LinearLayout buildBottomNavBar() {
    LinearLayout bar = new LinearLayout(this);
    bar.setBackgroundColor(COLOR_SURFACE);
    bar.setElevation(dp(8)); bar.setPadding(0, dp(4), 0, dp(4));
    navItems.clear();
    final String[] titles = {"Play", "Drivers", "Settings", "Content"};
    final String[] icons = {"ic_play_arrow", "ic_memory", "ic_settings", "ic_folder_open"};
    for (int i = 0; i < titles.length; i++) {
      LinearLayout item = new LinearLayout(this); item.setOrientation(LinearLayout.VERTICAL); item.setGravity(Gravity.CENTER); item.setPadding(0, dp(2), 0, dp(2));
      FrameLayout pill = new FrameLayout(this);
      LinearLayout.LayoutParams pillLp = lp(dp(56), dp(28));
      pillLp.bottomMargin = dp(2); pill.setLayoutParams(pillLp);
      ImageView icon = new ImageView(this);
      Drawable d = getSymbol(icons[i]);
      if (d != null) icon.setImageDrawable(d); pill.addView(icon, new FrameLayout.LayoutParams(dp(20), dp(20), Gravity.CENTER)); item.addView(pill);
      TextView lbl = label(titles[i], 11, COLOR_MUTED, false); lbl.setGravity(Gravity.CENTER); item.addView(lbl); item.setTag(Integer.valueOf(i)); item.setOnClickListener(this); bar.addView(item, lpWeight1());
      navItems.add(item);
    }
    updateNavSelection();
    return bar;
  }
  private void switchTab(int index) {
    if (index < 0 || index >= tabPages.size()) return;
    tabPages.get(currentTab).setVisibility(View.GONE);
    currentTab = index;
    prefs.edit().putInt("active_tab", index).apply();
    tabPages.get(currentTab).setVisibility(View.VISIBLE);
    updateNavSelection();
    refreshAllTabs();
    getWindow().getDecorView().performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
  }
  private void updateNavSelection() {
    for (int i = 0; i < navItems.size(); i++) {
      LinearLayout item = navItems.get(i);
      boolean active = (i == currentTab);
      FrameLayout pill = (FrameLayout) item.getChildAt(0); pill.setBackground(active ? cardBg(0xFF1F3828, 14) : null);
      ImageView iv = (ImageView) pill.getChildAt(0);
      if (iv != null && iv.getDrawable() != null) {
        iv.getDrawable().mutate().setTint(active ? colorAccent : COLOR_MUTED);
      }
      TextView tv = (TextView) item.getChildAt(1); tv.setTextColor(active ? colorAccent : COLOR_MUTED); tv.setTypeface(active ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
    }
  }
  private LinearLayout createStatTile(String cat, String val, String tag) {
    LinearLayout t = new LinearLayout(this); t.setOrientation(LinearLayout.VERTICAL); t.setBackground(ripple(0xFF1A241D, 0x28FFFFFF, 12)); t.setPadding(dp(12), dp(10), dp(12), dp(10));
    TextView c = label(cat.toUpperCase(Locale.ROOT), 10, 0xFF86968B, true); c.setLetterSpacing(0.06f); t.addView(c);
    TextView v = label(val, 13, Color.WHITE, true); v.setPadding(0, dp(2), 0, dp(2));
    v.setMaxLines(1); t.addView(v); t.setTag(tag); t.setOnClickListener(this);
    return t;
  }
  private LinearLayout createTileRow(View v1, View v2) {
    LinearLayout row = new LinearLayout(this);
    LinearLayout.LayoutParams lp = lp(MP, WC);
    lp.bottomMargin = dp(8); row.setLayoutParams(lp);
    LinearLayout.LayoutParams p1 = lpWeight1();
    p1.rightMargin = v2 != null ? dp(8) : 0; row.addView(v1, p1);
    if (v2 != null) row.addView(v2, lpWeight1());
    return row;
  }
  private void addBadgeRow(String c1, String v1, String t1, String c2, String v2, String t2) {
    activeBadgesLayout.addView(createTileRow(createStatTile(c1, v1, t1), createStatTile(c2, v2, t2)));
  }
  private void addInfoCard(LinearLayout content, String title, String text, String badge, int badgeFg, int badgeBg) {
    LinearLayout c = createCard(content, 14); c.addView(label(title, 13, COLOR_MUTED, true));
    LinearLayout r = new LinearLayout(this); r.setGravity(Gravity.CENTER_VERTICAL); r.setPadding(0, dp(6), 0, 0); r.addView(label(text, 12, COLOR_FOG, false), lpWeight1());
    TextView b = label(badge, 11, badgeFg, true); b.setBackground(cardBg(badgeBg, 8, COLOR_CARD_STROKE, 1)); b.setPadding(dp(8), dp(4), dp(8), dp(4)); r.addView(b); c.addView(r);
  }
  private View buildPlayTab() {
    LinearLayout content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
    LinearLayout hero = createCard(content, 18); hero.setBackground(cardBg(COLOR_CARD, 20, COLOR_HERO_STROKE, 1));
    gameTitleText = label("Forza Horizon (2012)", 20, COLOR_FOG, true); hero.addView(gameTitleText);
    statusPill = new LinearLayout(this); statusPill.setGravity(Gravity.CENTER_VERTICAL); statusPill.setPadding(dp(8), dp(4), dp(10), dp(4));
    LinearLayout.LayoutParams spl = lp(WC, WC); spl.setMargins(0, dp(6), 0, dp(14)); statusPill.setLayoutParams(spl);
    statusDot = new View(this);
    LinearLayout.LayoutParams dlp = lp(dp(8), dp(8)); dlp.rightMargin = dp(6); statusPill.addView(statusDot, dlp);
    gameStatusText = label("", 11, COLOR_MUTED, true); statusPill.addView(gameStatusText); hero.addView(statusPill);
    launchButton = new LinearLayout(this); launchButton.setGravity(Gravity.CENTER); launchButton.setBackground(ripple(colorAccent, 0x3CFFFFFF, 14)); launchButton.setPadding(dp(16), dp(11), dp(16), dp(11)); launchButton.setTag("play"); launchButton.setOnClickListener(this);
    launchIcon = new ImageView(this);
    LinearLayout.LayoutParams lip = lp(dp(20), dp(20)); lip.rightMargin = dp(8); launchButton.addView(launchIcon, lip);
    launchText = label("Play", 15, 0xFF0B1F11, true); launchText.setLetterSpacing(0.04f); launchButton.addView(launchText); hero.addView(launchButton);
    LinearLayout badges = createCard(content, 14);
    TextView bt = label("Active Launch Profile", 13, COLOR_MUTED, true); bt.setPadding(0, 0, 0, dp(8)); badges.addView(bt);
    activeBadgesLayout = new LinearLayout(this); activeBadgesLayout.setOrientation(LinearLayout.VERTICAL); badges.addView(activeBadgesLayout);
    String mfg = Build.MANUFACTURER;
    if (mfg != null && mfg.length() > 0) mfg = Character.toUpperCase(mfg.charAt(0)) + mfg.substring(1).toLowerCase(Locale.ROOT);
    String adreno = PinyonShiftActivity.adrenoModel();
    Intent bi = registerReceiver(null, new android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED));
    int bTemp = bi != null ? bi.getIntExtra(android.os.BatteryManager.EXTRA_TEMPERATURE, 0) : 0;
    String tStr = bTemp > 0 ? String.format(Locale.ROOT, " · %.1f°C", bTemp / 10.0f) : "";
    addInfoCard(content, "Hardware & Platform", (mfg != null ? mfg + " " : "") + Build.MODEL + " · Android " + Build.VERSION.RELEASE + tStr,
        adreno != null ? "Adreno " + adreno : "Vulkan GPU", colorAccent, 0xFF1A241D);
    addInfoCard(content, "Storage & Environment", "Free Storage: " + size(base.getUsableSpace()), "Save Protected", COLOR_SUCCESS, 0xFF14281E);
    return wrapScrollable(content);
  }
  private View buildDriversTab() {
    LinearLayout content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
    LinearLayout card = addSection(content, "Vulkan Driver Packages");
    activeDriverText = label("", 12, COLOR_MUTED, false); activeDriverText.setPadding(0, dp(4), 0, dp(10)); card.addView(activeDriverText);
    driverListContainer = new LinearLayout(this); driverListContainer.setOrientation(LinearLayout.VERTICAL); card.addView(driverListContainer);
    Button importBtn = createM3Button("+  Import Driver (.zip / .adpkg)", false); importBtn.setTag("import_driver"); importBtn.setOnClickListener(this); card.addView(importBtn);
    Button purgeBtn = createM3Button("Purge Shader Cache (Clean Rebuild)", false); purgeBtn.setTag("purge_shaders"); purgeBtn.setOnClickListener(this);
    LinearLayout.LayoutParams plp = lp(MP, WC); plp.topMargin = dp(8); purgeBtn.setLayoutParams(plp); card.addView(purgeBtn);
    return wrapScrollable(content);
  }
  private void refreshDriversList() {
    if (driverListContainer == null) return;
    driverListContainer.removeAllViews();
    String selected = prefs.getString("selected_driver", "auto");
    String adreno = PinyonShiftActivity.adrenoModel();
    String rec = PinyonShiftActivity.recommendedDriver(adreno);
    activeDriverText.setText("Active: " + ("system".equals(selected) ? "System" : selected) + ("auto".equals(selected) ? (rec != null ? " (" + rec + ")" : " (System)") : ""));
    addDriverItem("System Default Driver", "system", "System Vulkan stack (Qualcomm stock driver)", "system".equals(selected) || ("auto".equals(selected) && rec == null));
    addDriverItem("Auto Recommend", "auto", "Auto picks Turnip V37 on 6xx/7xx/8xx", "auto".equals(selected));
    File[] dirs = driversDir.listFiles();
    if (dirs != null) {
      Arrays.sort(dirs);
      for (File d : dirs) {
        if (d.isDirectory() && new File(d, "meta.json").isFile()) {
          String name = d.getName();
          addDriverItem(name, name, "Turnip / AdrenoTools package", name.equals(selected));
        }
      }
    }
  }
  private void addDriverItem(final String name, final String id, String desc, boolean isSelected) {
    LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL);
    int bg = isSelected ? ((colorAccent & 0x00FFFFFF) | 0x28000000) : COLOR_SURFACE;
    int stroke = isSelected ? colorAccent : COLOR_CARD_STROKE; row.setBackground(cardBg(bg, 12, stroke, 1)); row.setPadding(dp(12), dp(10), dp(12), dp(10));
    LinearLayout.LayoutParams l = lp(MP, WC); l.bottomMargin = dp(8); row.setLayoutParams(l);
    LinearLayout textGroup = new LinearLayout(this); textGroup.setOrientation(LinearLayout.VERTICAL); textGroup.addView(label(name + (isSelected ? "  (Active)" : ""), 13, isSelected ? colorAccent : COLOR_FOG, true)); textGroup.addView(label(desc, 11, COLOR_TEXT_DIM, false)); row.addView(textGroup, lpWeight1()); row.setTag("drv:" + id); row.setOnClickListener(this);
    if (!"auto".equals(id) && !"turnip-gen8-v37".equals(id)) {
      Button del = new Button(this); del.setText("X"); del.setTextColor(COLOR_RED);
      del.setBackgroundColor(Color.TRANSPARENT); del.setTag("del:" + id); del.setOnClickListener(this); row.addView(del);
    }
    driverListContainer.addView(row);
  }
  private void deleteDriver(final String id) {
    confirmDialog("Delete Driver", "Remove " + id + "?", "Delete", new DialogInterface.OnClickListener() {
      @Override
      public void onClick(DialogInterface d, int w) {
        PinyonShiftActivity.deleteTree(new File(driversDir, id));
        if (id.equals(prefs.getString("selected_driver", "auto"))) {
          prefs.edit().putString("selected_driver", "auto").apply();
        }
        refreshDriversList();
        applySettings();
      }
    });
  }
  private void importDriverZip() {
    Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
    intent.addCategory(Intent.CATEGORY_OPENABLE);
    intent.setType("*/*");
    intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/zip", "application/x-zip-compressed", "application/octet-stream"});
    try { startActivityForResult(intent, REQUEST_DRIVER_ZIP); } catch (Exception e) { toast("No file picker"); }
  }
  static final String[] ASPECT_ITEMS = {"Widescreen (Hor+)", "Fit (16:9)", "Stretch", "Crop"}, ASPECT_VALS = {"hor_plus", "letterbox", "stretch", "crop"};
  static final String[] RES_ITEMS = {"Native Display (1080p)", "720p (Direct Match)", "1440p (2x Internal)"}; static final int[] RES_VALS = {1080, 720, 1440};
  static final String[] FPS_ITEMS = {"30 FPS (Native)", "60 FPS", "45 FPS", "40 FPS", "120 FPS", "Unlocked"}; static final int[] FPS_VALS = {30, 60, 45, 40, 120, 0};
  static final String[] PRESET_ITEMS = {"Balanced", "Potato", "Ultra"}, PRESET_VALS = {"balanced", "potato", "ultra"};
  static final String[] UPSCALER_ITEMS = {"AMD FSR 1.0", "CAS", "Bilinear"}, UPSCALER_VALS = {"fsr", "cas", "bilinear"};
  static final String[] CTRL_ITEMS = {"Touch Arrows (Default)", "Tilt A (RR3 Gyro)", "Classic Pad", "Gamepad"}, CTRL_VALS = {"arrows", "tilt_a", "classic", "gamepad"};
  static final String[] OPACITY_ITEMS = {"100%", "75%", "50%", "25%", "Hidden"}; static final int[] OPACITY_VALS = {100, 75, 50, 25, 0};
  private View buildSettingsTab() {
    LinearLayout content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
    LinearLayout disp = addSection(content, "Display & Resolution");
    aspectModeSummary = addSettingSelector(disp, "Display Scaling Mode", "scaling");
    resScaleSummary = addSettingSelector(disp, "Internal Resolution", "res_scale");
    fpsCapSummary = addSettingSelector(disp, "Target Framerate", "fps");
    brightnessSummary = addSettingSelector(disp, "Display Brightness", "brightness");
    addSwitchRow(disp, "Vertical Sync (VSync)", "vsync", true);
    addSwitchRow(disp, "Performance Overlay", "fps_overlay", true);
    LinearLayout gfx = addSection(content, "Graphics & Shaders");
    presetSummary = addSettingSelector(gfx, "Graphics Preset", "preset");
    upscalerSummary = addSettingSelector(gfx, "Output Upscaler", "upscaler");
    themeSummary = addSettingSelector(gfx, "Theme Accent", "theme");
    addSwitchRow(gfx, "Qualcomm Adreno Turbo", "gpu_turbo", false);
    LinearLayout ctrl = addSection(content, "Controls & Haptics");
    controlSummary = addSettingSelector(ctrl, "Control Scheme", "controls");
    steerHeightSummary = addSettingSelector(ctrl, "Steering Buttons Height", "steer_height");
    steerInsetSummary = addSettingSelector(ctrl, "Steering Inset Margin", "steer_margin");
    touchOpacitySummary = addSettingSelector(ctrl, "Touch Controls Opacity", "touch_opacity");
    addSettingSelector(ctrl, "Touch Controls Guide", "touch_guide").setText("View 4-Layer Gesture Map");
    addSwitchRow(ctrl, "Steering Horizon", "touch_horizon", true);
    addSwitchRow(ctrl, "Look-Around Orbit (Center Drag)", PinyonShiftActivity.PREF_LOOK_AROUND, true);
    addSwitchRow(ctrl, "Tactile Haptics", "haptics", true);
    addSwitchRow(ctrl, "Smart Auto-Clutch", PinyonShiftActivity.PREF_SMART_CLUTCH, true);
    addSwitchRow(ctrl, "Center Gesture Shift", PinyonShiftActivity.PREF_GESTURE_SHIFT, true);
    addSwitchRow(ctrl, "HUD Touch Hitboxes", PinyonShiftActivity.PREF_HUD_HITBOXES, true);
    addSwitchRow(ctrl, "Menu Mode Auto-Switch", PinyonShiftActivity.PREF_MENU_MODE_AUTO, true);
    LinearLayout gm = addSection(content, "Game Features");
    addSwitchRow(gm, "Skip Opening Movies", "skip_movies", true);
    addSwitchRow(gm, "1000 Club Offline", "club_offline", true);
    addSwitchRow(gm, "Unlock Treasure Map", "treasure_map", true);
    addSwitchRow(gm, "Auto-Boot Game", "auto_launch", false);
    return wrapScrollable(content);
  }
  private TextView addSettingSelector(LinearLayout parent, String title, String tag) {
    LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL); row.setBackground(ripple(COLOR_SURFACE, 0x28FFFFFF, 10)); row.setPadding(dp(12), dp(10), dp(12), dp(10));
    LinearLayout.LayoutParams l = lp(MP, WC); l.topMargin = dp(6); row.setLayoutParams(l);
    LinearLayout tg = new LinearLayout(this); tg.setOrientation(LinearLayout.VERTICAL); tg.addView(label(title, 13, Color.WHITE, true));
    TextView vv = label("", 11, colorAccent, false); tg.addView(vv); row.addView(tg, lpWeight1()); row.addView(label("›", 16, COLOR_TEXT_DIM, false)); row.setTag(tag); row.setOnClickListener(this); parent.addView(row);
    return vv;
  }
  private void tintSwitch(Switch sw) {
    int[][] states = new int[][]{new int[]{android.R.attr.state_checked}, new int[]{-android.R.attr.state_checked}};
    sw.setThumbTintList(new ColorStateList(states, new int[]{colorAccent, COLOR_TEXT_DIM}));
    sw.setTrackTintList(new ColorStateList(states, new int[]{(colorAccent & 0x00FFFFFF) | 0x80000000, 0x3CFFFFFF}));
  }
  private void addSwitchRow(LinearLayout parent, String title, String key, boolean def) {
    LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(0, dp(4), 0, dp(6)); row.addView(label(title, 13, Color.WHITE, true), lpWeight1());
    Switch sw = new Switch(this); tintSwitch(sw); sw.setChecked(prefs.getBoolean(key, def)); sw.setTag(key); sw.setOnCheckedChangeListener(this); row.addView(sw); parent.addView(row);
  }
  @Override
  public void onCheckedChanged(CompoundButton b, boolean c) {
    String key = (String) b.getTag();
    if ("wifi_scan".equals(key)) {
      if (c) {
        if (discoveryText != null) discoveryText.setText("Searching for PC on local Wi-Fi...");
        startDiscovery();
      } else {
        discovering = false;
        if (discoveryText != null) discoveryText.setText("Wi-Fi discovery idle.");
      }
      return;
    }
    if (key != null) {
      prefs.edit().putBoolean(key, c).apply();
      applySettings();
    }
  }
  private void showDialog(String title, final String[] items, final int cur, final DialogInterface.OnClickListener ok) {
    LinearLayout c = new LinearLayout(this); final Dialog d = createCardDialog(title, c);
    for (int i = 0; i < items.length; i++) {
      final int idx = i;
      Button b = new Button(this); b.setText(items[i]); b.setTextSize(13); b.setAllCaps(false); b.setTextColor(i == cur ? 0xFF0B1F11 : Color.WHITE); b.setBackground(ripple(i == cur ? colorAccent : 0xFF212923, Color.argb(40, 255, 255, 255), 10)); b.setPadding(dp(12), dp(8), dp(12), dp(8));
      LinearLayout.LayoutParams lp = lp(MP, WC); lp.topMargin = dp(4); b.setLayoutParams(lp); b.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { d.dismiss(); ok.onClick(d, idx); } }); c.addView(b);
    }
    Button cancel = createM3Button("Cancel", false);
    LinearLayout.LayoutParams clp = lp(MP, WC); clp.topMargin = dp(10); cancel.setLayoutParams(clp); cancel.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { d.dismiss(); } }); c.addView(cancel); d.setContentView(c); d.show();
  }
  private void showChoiceDialog(String title, final String prefKey, final String[] items, final String[] values) {
    String currentVal = prefs.getString(prefKey, values[0]);
    int cur = 0;
    for (int i = 0; i < values.length; i++) if (values[i].equals(currentVal)) cur = i;
    showDialog(title, items, cur, new DialogInterface.OnClickListener() {
      @Override
      public void onClick(DialogInterface d, int w) {
        prefs.edit().putString(prefKey, values[w]).apply();
        d.dismiss();
        refreshAllTabs();
      }
    });
  }
  private void showIntChoiceDialog(String title, final String prefKey, final String[] items, final int[] values) {
    int currentVal = prefs.getInt(prefKey, values[0]);
    int cur = 0;
    for (int i = 0; i < values.length; i++) if (values[i] == currentVal) cur = i;
    showDialog(title, items, cur, new DialogInterface.OnClickListener() {
      @Override
      public void onClick(DialogInterface d, int w) {
        prefs.edit().putInt(prefKey, values[w]).apply();
        d.dismiss();
        if ("theme_accent".equals(prefKey)) { recreate(); return; }
        refreshAllTabs();
      }
    });
  }
  private void handleTagClick(String tag) {
    if ("preset".equals(tag)) showChoiceDialog("Graphics Preset", "graphics_preset", PRESET_ITEMS, PRESET_VALS);
    else if ("scaling".equals(tag)) showChoiceDialog("Display Scaling Mode", "aspect_mode", ASPECT_ITEMS, ASPECT_VALS);
    else if ("res_scale".equals(tag)) showIntChoiceDialog("Internal Resolution", "res_scale", RES_ITEMS, RES_VALS);
    else if ("brightness".equals(tag)) showBrightnessDialog();
    else if ("fps".equals(tag)) showIntChoiceDialog("Target Framerate", "fps_cap", FPS_ITEMS, FPS_VALS);
    else if ("upscaler".equals(tag)) showChoiceDialog("Upscaler (FSR / CAS)", "upscaler", UPSCALER_ITEMS, UPSCALER_VALS);
    else if ("controls".equals(tag)) showChoiceDialog("Control Scheme", "control_scheme", CTRL_ITEMS, CTRL_VALS);
    else if ("touch_opacity".equals(tag)) showIntChoiceDialog("Touch Controls Opacity", "touch_opacity", OPACITY_ITEMS, OPACITY_VALS);
    else if ("steer_height".equals(tag)) showIntChoiceDialog("Steering Buttons Height", "steer_y_pct",
        new String[]{"Comfort (65%)", "High (55%)", "Standard (72%)", "Low (82%)"}, new int[]{65, 55, 72, 82});
    else if ("steer_margin".equals(tag)) showIntChoiceDialog("Steering Inset Margin", "steer_x_dp",
        new String[]{"Normal (65dp)", "Edge (35dp)", "Thumb Inset (95dp)", "Deep Inset (130dp)"}, new int[]{65, 35, 95, 130});
    else if ("touch_guide".equals(tag)) PinyonShiftActivity.showTouchGuide(this);
    else if ("theme".equals(tag)) {
      showIntChoiceDialog("Theme Accent", "theme_accent",
          new String[]{"Pinyon Green", "Amber", "Alpine", "Cyan", "Sunset", "Dynamic"},
          new int[]{COLOR_ACCENT_DEFAULT, 0xFFF1AE36, COLOR_FOG, 0xFF5CE1E6, 0xFFFF7043, sysAccent});
    }
    else if ("driver".equals(tag)) switchTab(1);
    else if ("dump".equals(tag)) switchTab(3);
    else if ("play".equals(tag)) {
      if (gameReady()) startGame();
      else switchTab(3);
    }
    else if ("import_driver".equals(tag)) importDriverZip();
    else if ("import_folder".equals(tag)) chooseFolder();
    else if ("purge_shaders".equals(tag)) purgeShaders();
    else if ("backup_now".equals(tag)) manualBackup();
    else if ("clear_save".equals(tag)) clearActiveSave();
  }
  private void showBrightnessDialog() {
    LinearLayout c = new LinearLayout(this); final Dialog d = createCardDialog("Video Calibration - Brightness", c);
    c.addView(label("Adjust brightness until DARK is barely visible and BRIGHT is clear.", 11, COLOR_MUTED, false));
    LinearLayout bx = new LinearLayout(this); int bh = dp(44), sp = dp(6);
    int[] bgC = {0xFF0E1210, 0xFF505A54, 0xFFE0E8E2}, txC = {0xFF252E28, 0xFF88968E, 0xFFFFFFFF};
    String[] lbl = {"DARK", "MID", "BRIGHT"};
    for (int i = 0; i < 3; i++) {
      if (i > 0) { View s = new View(this); s.setLayoutParams(lp(sp, 1)); bx.addView(s); }
      LinearLayout b = new LinearLayout(this); b.setGravity(Gravity.CENTER); b.setBackground(cardBg(bgC[i], 8, bgC[i], 0));
      b.addView(label(lbl[i], 10, txC[i], true)); bx.addView(b, new LinearLayout.LayoutParams(0, bh, 1f));
    }
    c.addView(bx);
    final int cur = prefs.getInt("screen_brightness", 100);
    final TextView val = label("Brightness: " + cur + "%", 13, colorAccent, true);
    val.setGravity(Gravity.CENTER); val.setPadding(0, dp(8), 0, dp(4)); c.addView(val);
    final SeekBar sb = new SeekBar(this); sb.setMax(100); sb.setProgress(cur);
    sb.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
      @Override public void onProgressChanged(SeekBar s, int v, boolean u) {
        int n = Math.max(10, v); val.setText("Brightness: " + n + "%");
        if (getWindow() != null) { WindowManager.LayoutParams lp = getWindow().getAttributes(); lp.screenBrightness = n / 100f; getWindow().setAttributes(lp); }
      }
      @Override public void onStartTrackingTouch(SeekBar s) {}
      @Override public void onStopTrackingTouch(SeekBar s) {}
    });
    c.addView(sb);
    Button done = createM3Button("Done", true);
    LinearLayout.LayoutParams dlp = lp(MP, WC); dlp.topMargin = dp(10); done.setLayoutParams(dlp);
    done.setOnClickListener(new View.OnClickListener() {
      @Override public void onClick(View v) {
        prefs.edit().putInt("screen_brightness", Math.max(10, sb.getProgress())).apply();
        refreshSettingsTab(); d.dismiss();
      }
    });
    c.addView(done); d.show();
  }
  private static void setSummary(TextView v, String t) { if (v != null) v.setText(t); }
  private void refreshSettingsTab() {
    String asp = prefs.getString("aspect_mode", "hor_plus");
    setSummary(aspectModeSummary, "hor_plus".equals(asp) ? "Widescreen (Hor+)" : "letterbox".equals(asp) ? "Fit (16:9)" : "stretch".equals(asp) ? "Stretch" : "Crop");
    int r = prefs.getInt("res_scale", 1080);
    if (r <= 540) { r = 1080; prefs.edit().putInt("res_scale", 1080).apply(); }
    setSummary(resScaleSummary, r == 1440 ? "1440p (2x Internal)" : r == 720 ? "720p (Direct Match)" : "Native Display (1080p)");
    setSummary(brightnessSummary, prefs.getInt("screen_brightness", 100) + "%");
    int c = prefs.getInt("fps_cap", 30);
    setSummary(fpsCapSummary, c > 0 ? c + " FPS" : "Unlocked");
    String p = prefs.getString("graphics_preset", "balanced");
    setSummary(presetSummary, "potato".equals(p) ? "Potato" : "ultra".equals(p) ? "Ultra" : "Balanced");
    String u = prefs.getString("upscaler", "fsr");
    setSummary(upscalerSummary, "fsr".equals(u) ? "AMD FSR 1.0" : "cas".equals(u) ? "CAS" : "Bilinear");
    setSummary(themeSummary, colorAccent == 0xFFF1AE36 ? "Horizon Amber" : colorAccent == COLOR_ACCENT_DEFAULT ? "Pinyon Green" : "Custom Accent");
    String ctrl = prefs.getString("control_scheme", "arrows");
    setSummary(controlSummary, "arrows".equals(ctrl) ? "Touch Arrows" : "tilt_a".equals(ctrl) ? "Tilt A (RR3 Gyro)" : "classic".equals(ctrl) ? "Classic" : "Gamepad");
    int sY = prefs.getInt("steer_y_pct", 65);
    setSummary(steerHeightSummary, sY == 55 ? "High (55%)" : sY == 72 ? "Standard (72%)" : sY == 82 ? "Low (82%)" : "Comfort (65%)");
    int sX = prefs.getInt("steer_x_dp", 65);
    setSummary(steerInsetSummary, sX == 35 ? "Edge (35dp)" : sX == 95 ? "Thumb Inset (95dp)" : sX == 130 ? "Deep Inset (130dp)" : "Normal (65dp)");
    int op = prefs.getInt("touch_opacity", 100);
    setSummary(touchOpacitySummary, op == 0 ? "Hidden" : op + "%");
    applySettings();
  }
  private View buildContentTab() {
    LinearLayout content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
    LinearLayout game = addSection(content, "Game Data Files");
    folderPathText = label("", 11, COLOR_TEXT_DIM, false); folderPathText.setPadding(0, dp(4), 0, dp(8)); game.addView(folderPathText);
    Button importFolderBtn = createM3Button("Select Game Folder (default.xex)", "ic_folder_open", false); importFolderBtn.setTag("import_folder"); importFolderBtn.setOnClickListener(this); game.addView(importFolderBtn);
    LinearLayout wifi = addSection(content, "Sync from PC (Wi-Fi)");
    Switch scanSw = new Switch(this);
    scanSw.setText("Scan for PC on Wi-Fi"); scanSw.setTextColor(Color.WHITE); scanSw.setTextSize(13);
    tintSwitch(scanSw); scanSw.setTag("wifi_scan");
    scanSw.setOnCheckedChangeListener(this); wifi.addView(scanSw);
    discoveryText = label("Wi-Fi discovery idle.", 11, COLOR_MUTED, false); discoveryText.setPadding(0, dp(4), 0, dp(8)); wifi.addView(discoveryText);
    updateText = label("", 12, COLOR_ACCENT_DEFAULT, false);
    updateText.setPadding(0, dp(4), 0, dp(6));
    updateText.setVisibility(View.GONE);
    wifi.addView(updateText);
    updateButton = createM3Button("Install Update", false);
    updateButton.setTag("install_update");
    updateButton.setOnClickListener(this);
    updateButton.setVisibility(View.GONE);
    wifi.addView(updateButton);

    addressField = createField("PC Address (e.g. 192.168.1.50:47615)", InputType.TYPE_CLASS_TEXT); wifi.addView(addressField);
    codeField = createField("6-digit Pair Code from PC screen", InputType.TYPE_CLASS_NUMBER);
    codeField.setFilters(new InputFilter[]{new InputFilter.LengthFilter(6)});
    LinearLayout.LayoutParams clp = lp(MP, WC); clp.setMargins(0, dp(6), 0, dp(10)); codeField.setLayoutParams(clp); wifi.addView(codeField);
    groupsBox = new LinearLayout(this); groupsBox.setOrientation(LinearLayout.VERTICAL); wifi.addView(groupsBox);
    copyButton = createM3Button("Connect & Transfer", "ic_sync", true); copyButton.setOnClickListener(this); wifi.addView(copyButton);
    progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
    progress.setMax(1000); progress.setVisibility(View.GONE);
    LinearLayout.LayoutParams plp = lp(MP, dp(8)); plp.setMargins(0, dp(12), 0, dp(4)); progress.setLayoutParams(plp); wifi.addView(progress);
    progressText = label("", 11, COLOR_TEXT_DIM, false); wifi.addView(progressText);
    LinearLayout saveCard = addSection(content, "Save Management");
    saveStatusText = label("", 11, COLOR_TEXT_DIM, false); saveStatusText.setPadding(0, dp(2), 0, dp(6)); saveCard.addView(saveStatusText);
    LinearLayout btnRow = new LinearLayout(this);
    Button backupBtn = createM3Button("+ Backup Save Now", false); backupBtn.setTag("backup_now"); backupBtn.setOnClickListener(this); btnRow.addView(backupBtn, lpWeight1());
    View sp = new View(this); sp.setLayoutParams(lp(dp(8), 1)); btnRow.addView(sp);
    Button clearBtn = createM3Button("Reset Active Save", false); clearBtn.setTag("clear_save"); clearBtn.setOnClickListener(this); clearBtn.setTextColor(COLOR_RED); btnRow.addView(clearBtn, lpWeight1());
    saveCard.addView(btnRow);
    LinearLayout backupCard = addSection(content, "Save Backups");
    backupListContainer = new LinearLayout(this); backupListContainer.setOrientation(LinearLayout.VERTICAL); backupCard.addView(backupListContainer);
    return wrapScrollable(content);
  }
  private static long dirSize(File f) {
    if (f == null || !f.exists()) return 0;
    if (f.isFile()) return f.length();
    long sz = 0; File[] ch = f.listFiles();
    if (ch != null) for (File c : ch) sz += dirSize(c);
    return sz;
  }
  private void refreshBackupsList() {
    File user = new File(base, "state/user");
    long uSize = dirSize(user);
    if (saveStatusText != null) {
      saveStatusText.setText(uSize > 0 ? "Active Profile: Present (" + size(uSize) + ")" : "Active Profile: Clean (No active save)");
    }
    if (backupListContainer == null) return;
    backupListContainer.removeAllViews();
    File backups = new File(base, "state/backups/saves");
    File[] stamps = backups.listFiles();
    if (stamps == null || stamps.length == 0) {
      backupListContainer.addView(label("No save backups found", 11, COLOR_TEXT_DIM, false));
      return;
    }
    Arrays.sort(stamps, Collections.reverseOrder());
    for (final File s : stamps) {
      if (!s.isDirectory()) continue;
      LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(0, dp(4), 0, dp(4));
      row.addView(label(s.getName() + " (" + size(dirSize(s)) + ")", 12, Color.WHITE, false), lpWeight1());
      Button rst = new Button(this);
      rst.setText("Restore"); rst.setTextSize(11); rst.setTextColor(colorAccent);
      rst.setBackgroundColor(Color.TRANSPARENT); rst.setTag("rst:" + s.getName()); rst.setOnClickListener(this); row.addView(rst);
      Button del = new Button(this);
      del.setText("X"); del.setTextSize(11); del.setTextColor(COLOR_RED);
      del.setBackgroundColor(Color.TRANSPARENT); del.setTag("del_save:" + s.getName()); del.setOnClickListener(this); row.addView(del);
      backupListContainer.addView(row);
    }
  }
  private void manualBackup() {
    File user = new File(base, "state/user");
    if (!user.isDirectory() || dirSize(user) == 0) { toast("No active save to backup."); return; }
    String stamp = new java.text.SimpleDateFormat("yyyyMMdd'T'HHmmss'Z'", Locale.US).format(new java.util.Date());
    File backup = new File(base, "state/backups/saves/" + stamp);
    try {
      PinyonShiftActivity.copyTree(user, backup);
      toast("Save backed up to " + stamp);
    } catch (IOException e) { toast("Backup failed: " + e.getMessage()); }
    refreshBackupsList();
  }
  private void clearActiveSave() {
    confirmDialog("Reset Active Save", "Clear current active save profile? A backup will be created automatically before clearing.", "Reset", new DialogInterface.OnClickListener() {
      @Override
      public void onClick(DialogInterface d, int w) {
        backUpSave();
        PinyonShiftActivity.deleteTree(new File(base, "state/user"));
        toast("Active save cleared (backup created).");
        refreshBackupsList();
      }
    });
  }
  private void deleteSaveBackup(final String stamp) {
    confirmDialog("Delete Backup", "Delete backup " + stamp + "?", "Delete", new DialogInterface.OnClickListener() {
      @Override
      public void onClick(DialogInterface d, int w) {
        PinyonShiftActivity.deleteTree(new File(base, "state/backups/saves/" + stamp));
        toast("Backup deleted.");
        refreshBackupsList();
      }
    });
  }
  private void restoreSave(final File backup) {
    confirmDialog("Restore Save Backup", "Restore save from " + backup.getName() + "? Current save will be backed up.", "Restore", new DialogInterface.OnClickListener() {
      @Override
      public void onClick(DialogInterface d, int w) {
        backUpSave();
        try {
          PinyonShiftActivity.copyTree(backup, new File(base, "state/user"));
          toast("Save restored!");
        } catch (IOException e) {
          toast("Restore failed: " + e.getMessage());
        }
        refreshBackupsList();
      }
    });
  }
  private void purgeShaders() {
    confirmDialog("Purge Shader Cache", "Delete cached Vulkan pipelines and compiled shaders? Next launch will compile fresh pipelines.", "Purge", new DialogInterface.OnClickListener() {
      @Override
      public void onClick(DialogInterface d, int w) {
        PinyonShiftActivity.deleteTree(new File(base, "state/cache/shaders"));
        PinyonShiftActivity.deleteTree(new File(base, "state/cache/dumped_shaders"));
        new File(base, "state/cache/shaders").mkdirs();
        toast("Shader cache purged!");
      }
    });
  }
  private void refreshAllTabs() {
    boolean ready = gameReady();
    if (gameTitleText != null) gameTitleText.setText(ready ? "Forza Horizon (2012)" : "Set up your copy");
    if (statusPill != null && statusDot != null && gameStatusText != null) {
      statusPill.setBackground(cardBg(ready ? 0xFF14281E : 0xFF2A1618, 6)); statusDot.setBackground(cardBg(ready ? 0xFF5CE68B : 0xFFFF6B6B, 4));
      gameStatusText.setText(ready ? "Game Files Verified · Ready to Drive" : "Game Files Missing (default.xex)"); gameStatusText.setTextColor(ready ? 0xFF5CE68B : 0xFFFF6B6B);
    }
    if (launchButton != null) {
      launchText.setText(ready ? "Play" : "IMPORT GAME FILES");
      Drawable d = getSymbol(ready ? "ic_play_arrow" : "ic_folder_open");
      if (d != null) {
        d.setTint(0xFF0B1F11);
        launchIcon.setImageDrawable(d);
        launchIcon.setVisibility(View.VISIBLE);
      } else {
        launchIcon.setVisibility(View.GONE);
      }
    }
    if (activeBadgesLayout != null) {
      activeBadgesLayout.removeAllViews();
      String aspect = prefs.getString("aspect_mode", "hor_plus");
      String driver = prefs.getString("selected_driver", "auto");
      String preset = prefs.getString("graphics_preset", "balanced");
      String upscaler = prefs.getString("upscaler", "fsr");
      String ctrl = prefs.getString("control_scheme", "arrows");
      boolean vsync = prefs.getBoolean("vsync", true);
      int fps = prefs.getInt("fps_cap", 30);
      String presetStr = ("potato".equals(preset) ? "Potato" : "ultra".equals(preset) ? "Ultra" : "Balanced")
          + " · " + upscaler.toUpperCase(Locale.ROOT);
      String scalingStr = "hor_plus".equals(aspect) ? "Widescreen (Hor+)" : aspect;
      String fpsStr = (fps > 0 ? fps + " FPS" : "Max") + (vsync ? " · VSync" : "");
      String ctrlStr = "arrows".equals(ctrl) ? "Touch Arrows" : "tilt_a".equals(ctrl) ? "Tilt Gyro" : "classic".equals(ctrl) ? "Classic" : "Gamepad";
      String dataStr = ready ? "Verified" : "Missing";
      addBadgeRow("Preset", presetStr, "preset", "Display", scalingStr, "scaling");
      addBadgeRow("Framerate", fpsStr, "fps", "Driver", driver, "driver");
      addBadgeRow("Controls", ctrlStr, "controls", "Game Dump", dataStr, "dump");
    }
    if (folderPathText != null) {
      folderPathText.setText("Installed at: " + new File(base, "game/base").getAbsolutePath());
    }
    refreshDriversList();
    refreshSettingsTab();
    refreshBackupsList();
  }
  String[] buildCurrentArguments() {
    List<String> args = new ArrayList<>();
    String aspect = prefs.getString("aspect_mode", "hor_plus");
    args.add("--pinyon_shift_hor_plus=" + "hor_plus".equals(aspect));
    args.add("--present_letterbox=" + ("letterbox".equals(aspect) || "crop".equals(aspect)));
    if ("crop".equals(aspect)) args.add("--present_crop=true");
    String drv = prefs.getString("selected_driver", "auto");
    args.add("--android_gpu_driver=" + ("system".equals(drv) ? "" : drv));
    int res = prefs.getInt("res_scale", 1080);
    if (res <= 540) res = 1080;
    int scale = (res >= 1440) ? 2 : 1;
    args.add("--draw_resolution_scale_x=" + scale);
    args.add("--draw_resolution_scale_y=" + scale);
    args.add("--vsync=" + prefs.getBoolean("vsync", true));
    int fps = prefs.getInt("fps_cap", 30);
    args.add("--host_present_fps_limit=" + fps);
    args.add("--pinyon_shift_fh1_render_fps_limit=" + fps);
    String preset = prefs.getString("graphics_preset", "balanced");
    boolean potato = "potato".equals(preset);
    args.add("--pinyon_shift_fh1_env_map_rate=" + (potato ? "0.0" : "0.25"));
    args.add("--pinyon_shift_fh1_shadows=" + "ultra".equals(preset));
    args.add("--fh1_untile_predicated_tiling=true");
    args.add("--spirv_fast_pixel_math=true");
    args.add("--disable_bloom=true");
    args.add("--disable_motion_blur=true");
    args.add("--disable_depth_of_field=true");
    args.add("--anisotropic_override=-1");
    args.add("--fh1_msaa_single_sample=true");
    args.add("--vulkan_sparse=false");
    String upscaler = prefs.getString("upscaler", "fsr");
    args.add("--present_effect=" + ("fsr".equals(upscaler) ? "fsr" : "cas".equals(upscaler) ? "cas" : "bilinear"));
    if (prefs.getBoolean("skip_movies", true)) args.add("--pinyon_shift_skip_opening_movies=true");
    args.add("--pinyon_shift_dlc_treasure_map=" + prefs.getBoolean("treasure_map", true));
    if (prefs.getBoolean("gpu_turbo", false)) args.add("--android_gpu_turbo=true");
    if (prefs.getBoolean("club_offline", true)) {
      args.add("--pinyon_shift_car_challenge_gate_probe=true");
      args.add("--xam_report_live_signin=true");
    }
    args.add("--vulkan_shader_overrides=false");
    return args.toArray(new String[0]);
  }
  private void applySettings() {
    File aF = new File(base, ARGUMENTS_FILE); aF.getParentFile().mkdirs();
    try (OutputStream out = new FileOutputStream(aF)) {
      for (String a : buildCurrentArguments()) out.write((a + "\n").getBytes(StandardCharsets.UTF_8));
    } catch (IOException ignored) {}
    File cF = new File(base, CONFIG_TOML); cF.getParentFile().mkdirs();
    try (OutputStream out = new FileOutputStream(cF)) {
      String toml = "[display]\nscaling = \"" + prefs.getString("aspect_mode", "hor_plus") + "\"\nvsync = "
          + prefs.getBoolean("vsync", true) + "\nfps_limit = " + prefs.getInt("fps_cap", 60)
          + "\n\n[touch]\nscheme = \"" + prefs.getString("control_scheme", "arrows")
          + "\"\nopacity = " + prefs.getInt("touch_opacity", 100)
          + "\nhorizon = " + prefs.getBoolean("touch_horizon", true)
          + "\nhaptics = " + prefs.getBoolean("haptics", true)
          + "\n\n[dlc]\ntreasure_map = " + prefs.getBoolean("treasure_map", true) + "\n";
      out.write(toml.getBytes(StandardCharsets.UTF_8));
    } catch (IOException ignored) {}
  }
  private void chooseFolder() {
    Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
    try { startActivityForResult(intent, REQUEST_FOLDER); }
    catch (ActivityNotFoundException e) { toast("No document tree picker found"); }
  }
  @Override
  protected void onActivityResult(int req, int res, Intent data) {
    super.onActivityResult(req, res, data);
    if (res != RESULT_OK || data == null || data.getData() == null) return;
    if (req == REQUEST_FOLDER) {
      final Uri tree = data.getData();
      busy = true;
      getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
      progress.setVisibility(View.VISIBLE);
      new Thread(new Runnable() {
        @Override
        public void run() {
          try {
            importFolder(tree);
            finishOp("Game files imported!", true);
          } catch (IOException e) {
            finishOp("Import failed: " + e.getMessage(), false);
          }
        }
      }, "FolderImport").start();
    } else if (req == REQUEST_DRIVER_ZIP) {
      final Uri uri = data.getData();
      new Thread(new Runnable() {
        @Override
        public void run() {
          try {
            String n = unpackDriver(getContentResolver(), driversDir, uri);
            prefs.edit().putString("selected_driver", n).apply();
            runOnUiThread(new Runnable() {
              @Override
              public void run() { refreshDriversList(); }
            });
            toast("Driver imported & active!");
          } catch (IOException e) {
            toast("Driver import failed: " + e.getMessage());
          }
        }
      }, "ZipImport").start();
    }
  }
  private void finishOp(final String msg, final boolean ok) {
    busy = false;
    runOnUiThread(new Runnable() {
      @Override
      public void run() {
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (progress != null) {
          progress.setVisibility(View.GONE);
          if (ok) progress.setProgress(progress.getMax());
        }
        if (progressText != null) progressText.setText(msg);
        refreshAllTabs();
      }
    });
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
    for (Entry e : files) {
      game |= e.path.equals("default.xex");
      total += e.size;
    }
    if (!game) throw new IOException("Folder holds no default.xex");
    if (total > base.getUsableSpace() - (256L << 20)) {
      throw new IOException("Not enough free space: " + size(total) + " needed");
    }
    File inc = new File(base, INCOMPLETE);
    inc.getParentFile().mkdirs();
    new FileOutputStream(inc).close();
    long done = 0;
    int cnt = files.size();
    for (int i = 0; i < files.size(); i++) {
      Entry e = files.get(i);
      File t = destination("game/base/" + e.path);
      if (t.length() != e.size) {
        File p = new File(t.getPath() + ".part");
        t.getParentFile().mkdirs();
        final long bf = done, sm = total;
        final int num = i + 1, cn = cnt;
        try (InputStream in = getContentResolver().openInputStream(e.uri);
          OutputStream out = new FileOutputStream(p)) {
          if (in == null) throw new IOException("Cannot read " + e.path);
          copy(in, out, new Progress() {
            @Override
            public void written(long b) { report(bf + b, sm, num, cn); }
          });
        }
        if (p.length() != e.size) throw new IOException("Incomplete " + e.path);
        if (t.exists() && !t.delete()) throw new IOException("Cannot replace " + t);
        if (!p.renameTo(t)) throw new IOException("Cannot write " + t);
      }
      done += e.size;
    }
    inc.delete();
  }
  private void list(Uri tree, String doc, String pre, List<Entry> out) throws IOException {
    Uri ch = DocumentsContract.buildChildDocumentsUriUsingTree(tree, doc);
    try (Cursor c = getContentResolver().query(ch, new String[] {
        DocumentsContract.Document.COLUMN_DOCUMENT_ID,
        DocumentsContract.Document.COLUMN_DISPLAY_NAME,
        DocumentsContract.Document.COLUMN_MIME_TYPE,
        DocumentsContract.Document.COLUMN_SIZE}, null, null, null)) {
      if (c == null) throw new IOException("Cannot list folder");
      while (c.moveToNext()) {
        String id = c.getString(0);
        String nm = c.getString(1);
        if (nm == null || nm.isEmpty() || nm.equals(".") || nm.equals("..") || nm.contains("/")) continue;
        if (DocumentsContract.Document.MIME_TYPE_DIR.equals(c.getString(2))) {
          list(tree, id, pre + nm + "/", out);
        } else {
          out.add(new Entry(DocumentsContract.buildDocumentUriUsingTree(tree, id), pre + nm, c.getLong(3)));
        }
      }
    }
  }
  private File destination(String path) throws IOException {
    if (!(path.startsWith("game/base/") || path.startsWith("state/")) || path.contains("\\")) throw new IOException("unexpected path " + path);
    for (String part : path.split("/")) if (part.equals("..")) throw new IOException("unexpected path " + path);
    File target = new File(base, path);
    if (!target.getCanonicalPath().startsWith(base.getCanonicalPath() + File.separator)) throw new IOException("unexpected path " + path);
    return target;
  }
  private void backUpSave() {
    File user = new File(base, "state/user");
    if (!user.isDirectory()) return;
    String stamp = new java.text.SimpleDateFormat("yyyyMMdd'T'HHmmss'Z'", Locale.US).format(new java.util.Date());
    File backup = new File(base, "state/backups/saves/" + stamp);
    try { PinyonShiftActivity.copyTree(user, backup); } catch (IOException ignored) {}
  }
  private static void copy(InputStream in, OutputStream out, Progress p) throws IOException {
    byte[] buf = new byte[1 << 17];
    long w = 0;
    for (int r; (r = in.read(buf)) > 0; ) {
      out.write(buf, 0, r);
      w += r;
      if (p != null) p.written(w);
    }
  }
  interface Progress { void written(long bytes); }
  private void report(final long done, final long total, final int num, final int cnt) {
    runOnUiThread(new Runnable() {
      @Override
      public void run() {
        if (progress != null) progress.setProgress(total > 0 ? (int) (done * 1000 / total) : 0);
        if (progressText != null) {
          progressText.setText("Copying " + num + "/" + cnt + " (" + size(done) + " / " + size(total) + ")");
        }
      }
    });
  }
  private static String size(long b) {
    if (b < 1024) return b + " B";
    if (b < 1048576) return (b / 1024) + " KB";
    if (b < 1073741824) return String.format(Locale.ROOT, "%.1f MB", b / 1048576.0);
    return String.format(Locale.ROOT, "%.2f GB", b / 1073741824.0);
  }
  private void startDiscovery() {
    discovering = true;
    new Thread(new Runnable() {
      @Override public void run() {
        try (DatagramSocket socket = new DatagramSocket()) {
          socket.setSoTimeout(1500); socket.setBroadcast(true);
          byte[] payload = "PINYON-SHIFT-DISCOVER 1".getBytes(StandardCharsets.UTF_8);
          while (discovering && server == null) {
            for (InetAddress a : PinyonShiftActivity.broadcastAddresses()) {
              try { socket.send(new DatagramPacket(payload, payload.length, a, DISCOVERY_PORT)); } catch (IOException ignored) {}
            }
            byte[] buf = new byte[512]; DatagramPacket pkt = new DatagramPacket(buf, buf.length);
            try {
              socket.receive(pkt);
              String ans = new String(pkt.getData(), 0, pkt.getLength(), StandardCharsets.UTF_8).trim();
              if (ans.startsWith("PINYON-SHIFT-HERE 1")) {
                String[] pt = ans.split(" ");
                int port = pt.length >= 3 ? Integer.parseInt(pt[2]) : HTTP_PORT;
                final String found = pkt.getAddress().getHostAddress() + ":" + port;
                runOnUiThread(new Runnable() {
                  @Override public void run() {
                    if (addressField != null && addressField.getText().length() == 0) addressField.setText(found);
                    if (discoveryText != null) discoveryText.setText("Found PC: " + found);
                  }
                });
                break;
              }
            } catch (SocketTimeoutException ignored) {}
          }
        } catch (IOException ignored) {}
      }
    }, "PcDiscovery").start();
  }
  @Override
  public void onClick(View v) {
    Object tag = v.getTag();
    if (tag instanceof Integer) { switchTab(((Integer) tag).intValue()); return; }
    if (tag instanceof String) {
      String s = (String) tag;
      if (s.startsWith("drv:")) {
        prefs.edit().putString("selected_driver", s.substring(4)).apply();
        refreshDriversList();
        applySettings();
      } else if (s.startsWith("del:")) {
        deleteDriver(s.substring(4));
      } else if (s.startsWith("rst:")) {
        restoreSave(new File(base, "state/backups/saves/" + s.substring(4)));
      } else if (s.startsWith("del_save:")) {
        deleteSaveBackup(s.substring(9));
      } else {
        handleTagClick(s);
      }
      return;
    }
    if (v == copyButton) {
      if (busy) return;
      String raw = addressField.getText().toString().trim();
      if (raw.isEmpty()) { toast("Enter PC address"); return; }
      if (!raw.contains(":")) raw += ":" + HTTP_PORT;
      server = raw;
      if (manifest == null) connect(server);
      else startCopy();
    }
  }
  private void connect(final String hostPort) {
    busy = true; progressText.setText("Connecting to " + hostPort + "...");
    new Thread(new Runnable() {
      @Override public void run() {
        try {
          final JSONObject m = fetchManifest(hostPort);
          runOnUiThread(new Runnable() { @Override public void run() { busy = false; manifest = m; showGroups(m); } });
        } catch (IOException e) {
          busy = false; toast("Cannot connect: " + e.getMessage());
        }
      }
    }, "Connect").start();
  }
  private JSONObject fetchManifest(String hostPort) throws IOException {
    URL url = new URL("http://" + hostPort + "/pinyon-shift-manifest.json");
    HttpURLConnection con = (HttpURLConnection) url.openConnection();
    con.setConnectTimeout(4000); con.setReadTimeout(4000);
    try (InputStream in = con.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      PinyonShiftActivity.copy(in, out);
      return new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8));
    } catch (JSONException e) {
      throw new IOException("bad manifest json", e);
    }
  }
    private void showGroups(JSONObject m) {
    manifest = m;
    groupsBox.removeAllViews();
    groupChecks.clear();
    groupSets.clear();
    JSONArray groups = manifest != null ? manifest.optJSONArray("groups") : null;
    if (groups == null) return;
    boolean ready = gameReady();
    for (int i = 0; i < groups.length(); i++) {
      JSONObject group = groups.optJSONObject(i);
      if (group == null) continue;
      final String id = group.optString("id");
      CheckBox check = new CheckBox(this);
      check.setTextColor(Color.WHITE);
      check.setTextSize(12);
      String label = group.optString("label") + " (" + size(group.optLong("bytes")) + ")";
      if (id.equals("save")) {
        label += ": replaces active save (backed up first)";
      }
      String set = group.optString("set", "");
      if (!set.isEmpty()) {
        groupSets.put(id, set);
        label += ": synced with mod set";
      }
      check.setText(label);
      boolean selected = group.optBoolean("selected");
      if (id.equals("game")) {
        check.setChecked(!ready);
        check.setEnabled(ready);
      } else {
        check.setChecked(selected);
      }
      check.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
        @Override
        public void onCheckedChanged(CompoundButton view, boolean checked) {
          String linked = groupSets.get(id);
          if (linked != null && !linking) {
            linking = true;
            for (Map.Entry<String, CheckBox> entry : groupChecks.entrySet()) {
              if (linked.equals(groupSets.get(entry.getKey()))) entry.getValue().setChecked(checked);
            }
            linking = false;
          }
        }
      });
      groupsBox.addView(check);
      groupChecks.put(id, check);
    }
    showUpdate();
  }

  private void startCopy() {
    if (busy || manifest == null || server == null) return;
    final List<String> chosen = new ArrayList<>();
    for (Map.Entry<String, CheckBox> entry : groupChecks.entrySet()) {
      if (entry.getValue().isChecked()) chosen.add(entry.getKey());
    }
    if (chosen.isEmpty()) {
      toast("Select at least one category to transfer.");
      return;
    }
    busy = true;
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    progress.setVisibility(View.VISIBLE);
    final String code = codeField.getText().toString().trim();
    new Thread(new Runnable() {
      @Override
      public void run() {
        try {
          if (chosen.contains("save")) backUpSave();
          Set<String> modGroups = new HashSet<>();
          for (String id : chosen) if (groupSets.containsKey(id)) modGroups.add(id);
          JSONObject extras = manifest.optJSONObject("extras");
          JSONArray modsMirrored = extras != null ? extras.optJSONArray("mods_mirrored") : null;
          Set<String> mirrored = new HashSet<>();
          for (int i = 0; modsMirrored != null && i < modsMirrored.length(); i++) {
            mirrored.add(modsMirrored.optString(i));
          }
          if (!modGroups.isEmpty()) beginModSet(modGroups, mirrored);

          copyOverNetwork(code, server, chosen);

          if (!modGroups.isEmpty()) finishModSet();
          boolean titleUpdate = chosen.contains("title_update_v4");
          if (titleUpdate) {
            setClubArguments(true);
            toast("Title update v4 copied: 1000 Club offline enabled");
          }
          finishOp("Transfer completed successfully!", true);
        } catch (IOException e) {
          finishOp("Transfer failed: " + e.getMessage(), false);
        }
      }
    }, "NetworkCopy").start();
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
        setArguments(new String[] {"--pinyon_shift_car_challenge_gate_probe=true",
                "--xam_report_live_signin=true"}, club);
    }

    private boolean hasArguments(String[] flags) {
        File file = new File(base, ARGUMENTS_FILE);
        if (!file.isFile()) return false;
        try (InputStream in = new FileInputStream(file)) {
            List<String> lines = new ArrayList<>();
            for (String line : readAll(in).split("\n")) lines.add(line.trim());
            for (String flag : flags) {
                if (!lines.contains(flag)) return false;
            }
            return true;
        } catch (IOException error) {
            return false;
        }
    }

    // Adds or removes flags in the arguments file, keeping its other lines.
    private void setArguments(String[] flags, boolean on) throws IOException {
        File file = new File(base, ARGUMENTS_FILE);
        file.getParentFile().mkdirs();
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
        if (on) Collections.addAll(lines, flags);
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
    
  static String unpackDriver(android.content.ContentResolver res, File dir, Uri uri) throws IOException {
    String baseName = "driver";
    try (android.database.Cursor c = res.query(uri, new String[]{android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null)) {
      if (c != null && c.moveToFirst() && c.getString(0) != null) {
        baseName = c.getString(0).replaceAll("(?i)\\.(zip|adpkg)$", "")
                                 .replaceAll("[^A-Za-z0-9._-]+", "-").toLowerCase(Locale.ROOT);
      }
    }
    if (baseName.isEmpty() || baseName.startsWith(".")) baseName = "driver";
    File target = new File(dir, baseName);
    File staging = new File(dir, "." + baseName + ".importing");
    deleteTree(staging);
    staging.mkdirs();
    boolean library = false;
    try (InputStream raw = res.openInputStream(uri); java.util.zip.ZipInputStream zip = new java.util.zip.ZipInputStream(raw)) {
      for (java.util.zip.ZipEntry e; (e = zip.getNextEntry()) != null; zip.closeEntry()) {
        if (e.isDirectory()) continue;
        String fileName = new File(e.getName()).getName();
        if (fileName.isEmpty() || fileName.startsWith(".") || fileName.contains("..")) continue;
        library |= fileName.endsWith(".so");
        File out = new File(staging, fileName);
        try (OutputStream fos = new FileOutputStream(out)) {
          byte[] buf = new byte[8192];
          for (int r; (r = zip.read(buf)) > 0; ) fos.write(buf, 0, r);
        }
      }
    }
    if (!library) {
      deleteTree(staging);
      throw new IOException("the archive holds no driver library (.so)");
    }
    deleteTree(target);
    if (!staging.renameTo(target)) {
      throw new IOException("cannot create " + target);
    }
    return baseName;
  }

}
