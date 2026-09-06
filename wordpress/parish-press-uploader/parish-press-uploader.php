<?php
/**
 * Plugin Name: Parish Press Uploader
 * Description: Secure bulletin upload system with PWA support. No passwords - uses secure shareable links.
 * Version: 16.0.1
 * Author: Parish Press
 * Requires PHP: 7.0
 * License: GPL2
 */

// Prevent running on old PHP
if (version_compare(PHP_VERSION, '7.0', '<')) {
    add_action('admin_notices', function () {
        echo '<div class="notice notice-error"><p><strong>Parish Press Uploader</strong> requires PHP 7.0 or higher. You are running PHP ' . esc_html(PHP_VERSION) . '.</p></div>';
    });
    return;
}

if (!defined('ABSPATH')) exit;

define('PPU_DIR', WP_CONTENT_DIR . '/uploads/parish-bulletins/');
define('PPU_URL', content_url('/uploads/parish-bulletins/'));
define('PPU_ARCHIVE_DIR', WP_CONTENT_DIR . '/uploads/parish-bulletins-archive/');
define('PPU_ARCHIVE_URL', content_url('/uploads/parish-bulletins-archive/'));
define('PPU_VER', '16.0.1');
define('PPU_PLUGIN_FILE', __FILE__);


// ============================================================================
// STORAGE PATH HELPERS (AREA / DIOCESE / PARISH)
// ============================================================================
function ppu_get_diocese_area_slug($dio) {
    // Robust lookup: supports legacy installs where dioceses were keyed by name rather than slug
    $dio_slug = ppu_safe_slug($dio);
    if (!$dio_slug) return 'unassigned';

    $dioceses = get_option('ppu_dioceses', []);
    if (!is_array($dioceses)) $dioceses = [];

    // Direct key match (current format)
    if (isset($dioceses[$dio_slug]) && is_array($dioceses[$dio_slug])) {
        $area = sanitize_key($dioceses[$dio_slug]['area'] ?? 'unassigned');
        return $area ? $area : 'unassigned';
    }

    // Legacy match: compare against stored key slug and diocese name slug
    foreach ($dioceses as $k => $d) {
        if (!is_array($d)) continue;
        $k_slug = ppu_safe_slug($k);
        $n_slug = isset($d['name']) ? ppu_safe_slug($d['name']) : false;
        if (($k_slug && $k_slug === $dio_slug) || ($n_slug && $n_slug === $dio_slug)) {
            $area = sanitize_key($d['area'] ?? 'unassigned');
            return $area ? $area : 'unassigned';
        }
    }

    return 'unassigned';
}


function ppu_parish_relpath($dio, $par) {
    $dio = ppu_safe_slug($dio);
    $par = ppu_safe_slug($par);
    if (!$dio || !$par) return false;
    $area = ppu_get_diocese_area_slug($dio);
    return $area . '/' . $dio . '/' . $par;
}

function ppu_parish_dir($dio, $par) {
    $rel = ppu_parish_relpath($dio, $par);
    if (!$rel) return false;
    return trailingslashit(PPU_DIR . $rel);
}

function ppu_parish_url($dio, $par) {
    $rel = ppu_parish_relpath($dio, $par);
    if (!$rel) return false;
    return trailingslashit(PPU_URL . $rel);
}

/**
 * Back-compat resolver: older installs stored files in /{dio}/{par}/.
 * We still read from there when the new /{area}/{dio}/{par}/ is empty.
 */
function ppu_resolve_parish_storage($dio, $par) {
    $dio = ppu_safe_slug($dio);
    $par = ppu_safe_slug($par);
    if (!$dio || !$par) return ['dir' => false, 'url' => false, 'mode' => 'none'];

    $new_dir = ppu_parish_dir($dio, $par);
    $new_url = ppu_parish_url($dio, $par);

    $old_dir = trailingslashit(PPU_DIR . $dio . '/' . $par);
    $old_url = trailingslashit(PPU_URL . $dio . '/' . $par);

    $new_has = ($new_dir && is_dir($new_dir) && glob($new_dir . 'bulletin.*'));
    $old_has = (is_dir($old_dir) && glob($old_dir . 'bulletin.*'));

    if ($new_has) {
        return ['dir' => $new_dir, 'url' => $new_url, 'mode' => 'new'];
    }

    if ($old_has) {
        return ['dir' => $old_dir, 'url' => $old_url, 'mode' => 'old'];
    }

    return ['dir' => $new_dir, 'url' => $new_url, 'mode' => 'new'];
}



// ============================================================================
// MAINTENANCE: ENSURE EXPECTED FOLDER TREE EXISTS
// ============================================================================
function ppu_ensure_storage_tree($areas = null, $dioceses = null, $parishes = null) {
    if (!is_dir(PPU_DIR)) {
        wp_mkdir_p(PPU_DIR);
    }

    if (!is_array($areas)) $areas = ppu_get_areas();
    if (!is_array($dioceses)) $dioceses = ppu_get_dioceses(false);
    if (!is_array($parishes)) $parishes = ppu_get_parishes(false);

    foreach ($areas as $a_slug => $a_name) {
        $a_slug = sanitize_key($a_slug);
        if ($a_slug) {
            wp_mkdir_p(trailingslashit(PPU_DIR . $a_slug));
        }
    }

    foreach ($dioceses as $d_slug => $d) {
        if (!is_array($d)) continue;
        $d_slug = ppu_safe_slug($d_slug);
        if (!$d_slug) continue;
        $a_slug = sanitize_key($d['area'] ?? 'unassigned');
        if (!$a_slug) $a_slug = 'unassigned';
        wp_mkdir_p(trailingslashit(PPU_DIR . $a_slug . '/' . $d_slug));
    }

    foreach ($parishes as $p_slug => $p) {
        if (!is_array($p) || !isset($p['diocese'])) continue;
        $p_slug = ppu_safe_slug($p_slug);
        if (!$p_slug) continue;
        $d_slug = ppu_safe_slug($p['diocese']);
        if (!$d_slug) $d_slug = 'unassigned';
        $dir = ppu_parish_dir($d_slug, $p_slug);
        if ($dir) {
            wp_mkdir_p($dir);
        }
    }
}

// ============================================================================
// SECURITY HELPERS
// ============================================================================

function ppu_safe_slug($slug) {
    $slug = sanitize_title($slug);
    if (!preg_match('/^[a-z0-9\-]+$/', $slug)) return false;
    return $slug;
}

function ppu_filter_parish_public($arr) {
    $filtered = [];
    foreach ($arr as $slug => $entry) {
        if (is_array($entry) && isset($entry['name'], $entry['diocese'])) {
            $filtered[$slug] = [
                'name' => esc_html($entry['name']),
                'diocese' => esc_html($entry['diocese'])
            ];
        }
    }
    return $filtered;
}

function ppu_filter_diocese_public($arr) {
    $filtered = [];
    foreach ($arr as $slug => $entry) {
        if (is_array($entry) && isset($entry['name'])) {
            $filtered[$slug] = ['name' => esc_html($entry['name'])];
        }
    }
    return $filtered;
}

/**
 * Rate limiting to protect against abuse if link leaks
 */
function ppu_check_rate_limit($parish_slug, $action = 'upload') {
    $key = 'ppu_rate_' . $action . '_' . $parish_slug;
    $attempts = get_transient($key);
    
    if ($attempts === false) {
        set_transient($key, 1, 60); // 1 minute window
        return true;
    }
    
    if ($attempts >= 10) { // Max 10 uploads per minute
        return false;
    }
    
    set_transient($key, $attempts + 1, 60);
    return true;
}

/**
 * Log upload activity for audit trail
 */
function ppu_log_upload($dio, $par, $success = true) {
    $dir = ppu_parish_dir($dio, $par);
    if ($dir && !is_dir($dir)) wp_mkdir_p($dir);
    $log_file = $dir . 'upload-log.json';
    $log = file_exists($log_file) ? json_decode(file_get_contents($log_file), true) : [];
    if (!is_array($log)) $log = [];
    
    $log[] = [
        'time' => current_time('mysql'),
        'ip' => substr(hash('sha256', $_SERVER['REMOTE_ADDR'] ?? 'unknown'), 0, 16), // Hashed for privacy
        'success' => $success,
        'user_agent' => substr($_SERVER['HTTP_USER_AGENT'] ?? '', 0, 100)
    ];
    
    // Keep only last 100 entries
    $log = array_slice($log, -100);
    file_put_contents($log_file, json_encode($log, JSON_PRETTY_PRINT));
}

// ============================================================================
// DATA HELPERS
// ============================================================================

function ppu_get_areas() {
    $defaults = ['unassigned' => 'Unassigned Area'];
    $areas = get_option('ppu_areas', $defaults);
    return (is_array($areas) && !empty($areas)) ? $areas : $defaults;
}

function ppu_get_dioceses($public = false) {
    $dioceses = get_option('ppu_dioceses', []);
    if (!is_array($dioceses)) $dioceses = [];
    if ($public) return ppu_filter_diocese_public($dioceses);
    return $dioceses;
}

function ppu_get_parishes($public = false) {
    $parishes = get_option('ppu_parishes', []);
    if (!is_array($parishes)) $parishes = [];
    $dirty = false;
    foreach($parishes as $slug => $data) {
        if (!is_array($data)) {
            $parishes[$slug] = [
                'name' => (string)$data,
                'diocese' => 'armagh', 
                'key' => bin2hex(random_bytes(16))
            ]; 
            $dirty = true;
        } elseif (!isset($data['name']) || !isset($data['diocese']) || !isset($data['key'])) {
            $parishes[$slug]['name'] = isset($data['name']) ? $data['name'] : ucfirst($slug);
            $parishes[$slug]['diocese'] = isset($data['diocese']) ? $data['diocese'] : 'unassigned';
            $parishes[$slug]['key'] = isset($data['key']) ? $data['key'] : bin2hex(random_bytes(16));
            $dirty = true;
        }
    }
    if ($dirty) update_option('ppu_parishes', $parishes);
    if ($public) return ppu_filter_parish_public($parishes);
    return $parishes;
}

function ppu_get_settings() {
    $defaults = [
        'max_file_size_mb' => 50, 
        'max_pages' => 50,
        'key_created' => [] // Track when keys were created for rotation reminders
    ];
    $settings = get_option('ppu_settings', $defaults);
    return array_merge($defaults, is_array($settings) ? $settings : []);
}

// ============================================================================
// ARCHIVE HELPERS
// ============================================================================
function ppu_upcoming_sunday_date($ts = null) {
    if ($ts === null) $ts = current_time('timestamp');
    $w = (int) date('w', $ts); // 0=Sun
    if ($w === 0) return date('Y-m-d', $ts);
    $days = 7 - $w;
    return date('Y-m-d', strtotime('+' . $days . ' days', $ts));
}

function ppu_guess_sunday_date_from_ts($ts) {
    $w = (int) date('w', $ts);
    if ($w === 0) return date('Y-m-d', $ts);
    return date('Y-m-d', strtotime('last sunday', $ts));
}

function ppu_parish_archive_relpath($dio, $par) {
    $rel = ppu_parish_relpath($dio, $par);
    return $rel ? $rel : false;
}

function ppu_parish_archive_dir($dio, $par, $year = null) {
    $rel = ppu_parish_archive_relpath($dio, $par);
    if (!$rel) return false;
    $dir = trailingslashit(PPU_ARCHIVE_DIR . $rel);
    if ($year) $dir = trailingslashit($dir . intval($year));
    return $dir;
}

function ppu_parish_archive_url($dio, $par, $year = null) {
    $rel = ppu_parish_archive_relpath($dio, $par);
    if (!$rel) return false;
    $url = trailingslashit(PPU_ARCHIVE_URL . $rel);
    if ($year) $url = trailingslashit($url . intval($year));
    return $url;
}

function ppu_archive_add_drive_link($parish_slug, $year, $url) {
    $parish_slug = ppu_safe_slug($parish_slug);
    $year = intval($year);
    if (!$parish_slug || $year < 2000) return false;

    // Only store a proper URL
    $url = esc_url_raw($url);
    if (!$url) return false;

    $links = get_option('ppu_drive_links', []);
    if (!is_array($links)) $links = [];
    if (!isset($links[$parish_slug]) || !is_array($links[$parish_slug])) $links[$parish_slug] = [];

    $links[$parish_slug][strval($year)] = $url;
    update_option('ppu_drive_links', $links);
    return true;
}

function ppu_archive_get_drive_link($parish_slug, $year) {
    $parish_slug = ppu_safe_slug($parish_slug);
    $year = intval($year);
    if (!$parish_slug || $year < 2000) return '';

    $links = get_option('ppu_drive_links', []);
    if (!is_array($links)) return '';

    return isset($links[$parish_slug][strval($year)]) ? esc_url($links[$parish_slug][strval($year)]) : '';
}

function ppu_archive_store_last_sunday($dio, $par, $date_ymd) {
    $k = ppu_safe_slug($dio) . '/' . ppu_safe_slug($par);
    if (!$k) return;
    $data = get_option('ppu_last_sunday', []);
    if (!is_array($data)) $data = [];
    $data[$k] = sanitize_text_field($date_ymd);
    update_option('ppu_last_sunday', $data);
}

function ppu_archive_get_last_sunday($dio, $par) {
    $k = ppu_safe_slug($dio) . '/' . ppu_safe_slug($par);
    if (!$k) return '';
    $data = get_option('ppu_last_sunday', []);
    if (!is_array($data)) return '';
    return isset($data[$k]) ? sanitize_text_field($data[$k]) : '';
}

function ppu_archive_move_file($dio, $par, $src_file, $date_ymd) {
    $dio = ppu_safe_slug($dio);
    $par = ppu_safe_slug($par);
    if (!$dio || !$par || !is_file($src_file)) return false;

    $year = intval(substr($date_ymd, 0, 4));
    if ($year < 2000) $year = intval(date('Y'));

    $ext = strtolower(pathinfo($src_file, PATHINFO_EXTENSION));
    $target_dir = ppu_parish_archive_dir($dio, $par, $year);
    if (!$target_dir) return false;

    wp_mkdir_p($target_dir);
    if (!file_exists(trailingslashit($target_dir) . 'index.html')) {
        @file_put_contents(trailingslashit($target_dir) . 'index.html', '');
    }

    $base = sanitize_file_name($date_ymd . '.' . $ext);
    $target = trailingslashit($target_dir) . $base;

    // Handle duplicate filenames by adding -2, -3, etc.
    if (file_exists($target)) {
        $i = 2;
        while (file_exists(trailingslashit($target_dir) . $date_ymd . '-' . $i . '.' . $ext)) {
            $i++;
        }
        $target = trailingslashit($target_dir) . $date_ymd . '-' . $i . '.' . $ext;
    }
     // Try rename first
    if (@rename($src_file, $target)) {
        return $target;
    }

    // Fallback: copy then delete (useful for cross-filesystem moves)
    if (@copy($src_file, $target)) {
        @unlink($src_file);
        return $target;
    }

    // Log once for troubleshooting
    error_log('[PPU] Archive move failed: ' . $src_file . ' -> ' . $target);
    return false;
}
function ppu_archive_scan($dio, $par) {
    $dio = ppu_safe_slug($dio);
    $par = ppu_safe_slug($par);
    $out = [];

    $base = ppu_parish_archive_dir($dio, $par);
    if (!$base || !is_dir($base)) return $out;

    $years = glob(trailingslashit($base) . '[0-9][0-9][0-9][0-9]', GLOB_ONLYDIR);
    if (!$years) return $out;

    foreach ($years as $y_dir) {
        $y = basename($y_dir);
        $files = glob(trailingslashit($y_dir) . '*.*');
        if (!$files) continue;
        foreach ($files as $f) {
            $bn = basename($f);
            if (!preg_match('/^(\d{4}-\d{2}-\d{2})(?:-\d+)?\.(pdf|jpe?g|png|docx?)$/i', $bn, $m)) continue;
            $date = $m[1];
            $ext = strtolower($m[2]);
            $ts = strtotime($date);
            if (!$ts) continue;
            $month = date('Y-m', $ts);
            if (!isset($out[$y])) $out[$y] = [];
            if (!isset($out[$y][$month])) $out[$y][$month] = [];
            $out[$y][$month][] = ['date' => $date, 'ext' => $ext, 'file' => $f];
        }
    }

    krsort($out);
    foreach ($out as $y => $months) {
        krsort($out[$y]);
        foreach ($out[$y] as $m => $arr) {
            usort($arr, function($a,$b){ return strcmp($b['date'], $a['date']); });
            $out[$y][$m] = $arr;
        }
    }

    return $out;
}

function ppu_archive_calc_sizes($dio, $par) {
    $tree = ppu_archive_scan($dio, $par);
    $sizes = ['total_bytes' => 0, 'years' => []];
    foreach ($tree as $y => $months) {
        $y_bytes = 0;
        foreach ($months as $m => $items) {
            foreach ($items as $it) {
                $y_bytes += @filesize($it['file']) ?: 0;
            }
        }
        $sizes['years'][$y] = $y_bytes;
        $sizes['total_bytes'] += $y_bytes;
    }
    return $sizes;
}

function ppu_mb($bytes) {
    return round($bytes / 1024 / 1024, 1);
}

// ============================================================================
// STATISTICS
// ============================================================================

function ppu_log_view($dio, $par) {
    $dio = ppu_safe_slug($dio);
    $par = ppu_safe_slug($par);
    if (!$dio || !$par) return;

    // Ignore common bots/previews
    $ua = strtolower($_SERVER['HTTP_USER_AGENT'] ?? '');
    if ($ua && preg_match('/(bot|crawl|spider|slurp|facebookexternalhit|whatsapp|telegram|preview)/i', $ua)) {
        return;
    }

    // Store stats beside the bulletin location (new or legacy)
    $store = ppu_resolve_parish_storage($dio, $par);
    $dir = $store['dir'] ? $store['dir'] : ppu_parish_dir($dio, $par);
    if (!$dir) return;

    $file = trailingslashit($dir) . 'stats.json';
    if (!is_dir(dirname($file))) wp_mkdir_p(dirname($file));

    $stats = file_exists($file) ? json_decode(file_get_contents($file), true) : [];
    if (!is_array($stats)) $stats = [];

    $y = date('Y');
    $m = date('Y-m');
    $w = date('Y-W');

    if (!isset($stats[$y])) $stats[$y] = 0;
    if (!isset($stats[$m])) $stats[$m] = 0;
    if (!isset($stats[$w])) $stats[$w] = 0;

    $stats[$y]++;
    $stats[$m]++;
    $stats[$w]++;

    // Cleanup old month entries (keep ~2 years)
    foreach ($stats as $k => $v) {
        if (strpos($k, '-') !== false && $k < date('Y-m', strtotime('-2 years'))) unset($stats[$k]);
    }

    file_put_contents($file, json_encode($stats));
}


function ppu_get_stats($dio, $par) {
    $dio = ppu_safe_slug($dio);
    $par = ppu_safe_slug($par);
    if (!$dio || !$par) return ['w'=>0, 'm'=>0, 'y'=>0];

    $store = ppu_resolve_parish_storage($dio, $par);
    $dir = $store['dir'] ? $store['dir'] : ppu_parish_dir($dio, $par);
    if (!$dir) return ['w'=>0, 'm'=>0, 'y'=>0];

    $file = trailingslashit($dir) . 'stats.json';
    if (!file_exists($file)) return ['w'=>0, 'm'=>0, 'y'=>0];

    $stats = json_decode(file_get_contents($file), true);
    if (!is_array($stats)) $stats = [];

    $w = date('Y-W');
    $m = date('Y-m');
    $y = date('Y');

    return [
        'w' => isset($stats[$w]) ? intval($stats[$w]) : 0,
        'm' => isset($stats[$m]) ? intval($stats[$m]) : 0,
        'y' => isset($stats[$y]) ? intval($stats[$y]) : 0
    ];
}


// ============================================================================
// ACTIVATION
// ============================================================================

function ppu_activate() {
    if (!is_dir(PPU_DIR)) wp_mkdir_p(PPU_DIR);
    if (!file_exists(PPU_DIR . 'index.html')) file_put_contents(PPU_DIR . 'index.html', '');

    $htaccess = <<<HT
Options -Indexes

<FilesMatch "^(stats\.json|upload-log\.json|\.lock|index\.html)$">
<IfModule mod_authz_core.c>
Require all denied
</IfModule>
<IfModule !mod_authz_core.c>
Order allow,deny
Deny from all
</IfModule>
</FilesMatch>

<FilesMatch "\.(php|phtml|phar|cgi|pl|asp|aspx)$">
<IfModule mod_authz_core.c>
Require all denied
</IfModule>
<IfModule !mod_authz_core.c>
Order allow,deny
Deny from all
</IfModule>
</FilesMatch>

<IfModule mod_headers.c>
<FilesMatch "^bulletin\.(pdf|docx?|jpe?g|png)$">
Header set Cache-Control "no-store, no-cache, must-revalidate, max-age=0"
Header set Pragma "no-cache"
Header set Expires "0"
</FilesMatch>
</IfModule>
HT;

    file_put_contents(PPU_DIR . '.htaccess', $htaccess);

    if (!is_dir(PPU_ARCHIVE_DIR)) wp_mkdir_p(PPU_ARCHIVE_DIR);
    if (!file_exists(PPU_ARCHIVE_DIR . 'index.html')) file_put_contents(PPU_ARCHIVE_DIR . 'index.html', '');

    $aht = <<<HT
Options -Indexes

<FilesMatch "\.(php|phtml|phar|cgi|pl|asp|aspx)$">
<IfModule mod_authz_core.c>
Require all denied
</IfModule>
<IfModule !mod_authz_core.c>
Order allow,deny
Deny from all
</IfModule>
</FilesMatch>

<IfModule mod_headers.c>
<FilesMatch "\.(pdf|docx?|jpe?g|png)$">
Header set Cache-Control "no-store, no-cache, must-revalidate, max-age=0"
Header set Pragma "no-cache"
Header set Expires "0"
</FilesMatch>
</IfModule>
HT;

    file_put_contents(PPU_ARCHIVE_DIR . '.htaccess', $aht);

    ppu_rewrites();
    flush_rewrite_rules();
}

register_activation_hook(__FILE__, 'ppu_activate');

function ppu_deactivate() {
    flush_rewrite_rules();
}
register_deactivation_hook(__FILE__, 'ppu_deactivate');

// ============================================================================
// REWRITES AND QUERY VARS
// ============================================================================

function ppu_rewrites() {
    add_rewrite_rule('^bulletin/([a-z0-9\-]+)/([a-z0-9\-]+)/?', 'index.php?ppu_dio=$matches[1]&ppu_par=$matches[2]', 'top');
    add_rewrite_rule('^bulletin-upload/([a-z0-9\-]+)/([a-z0-9\-]+)/?', 'index.php?ppu_up_dio=$matches[1]&ppu_up_par=$matches[2]', 'top');
    add_rewrite_rule('^bulletin-zip/([a-z0-9\-]+)/([a-z0-9\-]+)/([0-9]{4})/?', 'index.php?ppu_zip_dio=$matches[1]&ppu_zip_par=$matches[2]&ppu_zip_year=$matches[3]', 'top');
}

add_action('init', 'ppu_rewrites');

function ppu_query_vars($v) {
    return array_merge($v, ['ppu_dio', 'ppu_par', 'ppu_up_dio', 'ppu_up_par', 'ppu_manifest', 'ppu_sw', 'ppu_qr']);
}
add_filter('query_vars', 'ppu_query_vars');

// ============================================================================
// SHORTCODE - PUBLIC PARISH FINDER
// ============================================================================

function ppu_shortcode_finder() {
    $dioceses = ppu_get_dioceses(true); 
    $parishes = ppu_get_parishes(true);
    ob_start(); 
    ?>
    <div class="ppu-finder">
        <input type="text" id="ppu-public-search" placeholder="Search for your parish..." style="width:100%;padding:12px;font-size:16px;border:1px solid #ccc;border-radius:4px;margin-bottom:15px;">
        <div id="ppu-results"></div>
    </div>
    <script>
    (function(){
        var ps = <?php echo json_encode($parishes); ?>;
        var ds = <?php echo json_encode($dioceses); ?>;
        var inp = document.getElementById('ppu-public-search');
        var res = document.getElementById('ppu-results');
        inp.addEventListener('input', function(e){
            var q = e.target.value.toLowerCase();
            var html = '';
            if(q.length > 1) {
                var found = 0;
                for(var k in ps) {
                    if(!ps[k] || !ps[k].name || !ps[k].diocese) continue;
                    if(ps[k].name.toLowerCase().includes(q)) {
                        var url = '<?php echo esc_url(site_url('bulletin/')); ?>' + encodeURIComponent(ps[k].diocese) + '/' + encodeURIComponent(k);
                        var dio_name = ds[ps[k].diocese] && ds[ps[k].diocese]['name'] ? ds[ps[k].diocese]['name'] : 'Unknown Diocese';
                        html += '<div style="background:#fff;border:1px solid #eee;padding:10px;margin-bottom:5px;border-radius:4px;">';
                        html += '<a href="'+url+'" target="_blank" style="text-decoration:none;font-weight:bold;color:#0073aa;display:block;">'+ps[k].name+'</a>';
                        html += '<span style="font-size:12px;color:#666;">'+dio_name+'</span>';
                        html += '</div>';
                        found++; if(found > 10) break;
                    }
                }
                if(found === 0) html = '<div style="color:#666;">No parishes found.</div>';
            }
            res.innerHTML = html;
        });
    })();
    </script>
    <?php 
    return ob_get_clean();
}
add_shortcode('parish_finder', 'ppu_shortcode_finder');

// ============================================================================
// TEMPLATE REDIRECT - MAIN ROUTING
// ============================================================================

function ppu_template_redirect() {
    
    // SERVICE WORKER
    if (get_query_var('ppu_sw')) {
        header('Content-Type: application/javascript');
        header('Service-Worker-Allowed: /bulletin-upload/');
        ?>
const CACHE_NAME = 'ppu-v<?php echo PPU_VER; ?>';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll([
                'https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js'
            ]);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => Promise.all(
            keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    const url = event.request.url || '';
    if (url.indexOf('/wp-admin') !== -1 || url.indexOf('/wp-json') !== -1) return;

    // Network first, fallback to cache (upload page assets only)
    event.respondWith(
        fetch(event.request)
            .then(response => {
                if (response.status === 200 && url.indexOf('pdf-lib') !== -1) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseClone);
                    });
                }
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
        <?php
        exit;
    }

    // PWA MANIFEST
    if (get_query_var('ppu_manifest')) {
        $name = isset($_GET['name']) ? sanitize_text_field($_GET['name']) : 'Bulletin';
        $start = isset($_GET['start']) ? esc_url_raw($_GET['start']) : './';
        
        header('Content-Type: application/manifest+json');
        echo json_encode([
            'name' => $name . ' Uploader',
            'short_name' => 'Upload',
            'description' => 'Upload bulletins for ' . $name,
            'start_url' => $start,
            'scope' => '/',
            'display' => 'standalone',
            'background_color' => '#f0f2f5',
            'theme_color' => '#0073aa',
            'orientation' => 'portrait',
            'icons' => [
                [
                    'src' => 'data:image/svg+xml,' . rawurlencode('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect fill="#0073aa" width="512" height="512" rx="64"/><path fill="#fff" d="M256 96L128 192v192h80V288h96v96h80V192L256 96z"/></svg>'),
                    'sizes' => '512x512',
                    'type' => 'image/svg+xml',
                    'purpose' => 'any maskable'
                ],
                [
                    'src' => 'data:image/svg+xml,' . rawurlencode('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192"><rect fill="#0073aa" width="192" height="192" rx="24"/><path fill="#fff" d="M96 36L48 72v84h30v-36h36v36h30V72L96 36z"/></svg>'),
                    'sizes' => '192x192',
                    'type' => 'image/svg+xml'
                ]
            ]
        ], JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
        exit;
    }
    
    // QR CODE PRINTER
    if (isset($_GET['ppu_qr'])) {
        $slug = ppu_safe_slug($_GET['ppu_qr']);
        $parishes = ppu_get_parishes();
        if($slug && isset($parishes[$slug]) && is_array($parishes[$slug])) {
            $p = $parishes[$slug];
            $d_slug = isset($p['diocese']) ? $p['diocese'] : '';
            $url = esc_url(site_url('bulletin/'.rawurlencode($d_slug)."/{$slug}"));
            ?>
            <!DOCTYPE html>
            <html><head>
                <meta charset="UTF-8">
                <title>QR: <?php echo esc_html($p['name']); ?></title>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
                <style>
                    body{font-family:sans-serif;text-align:center;padding:40px;} 
                    .box{border:2px solid #000;padding:40px;display:inline-block;border-radius:20px;} 
                    h1{margin-bottom:10px;font-size:32px;} 
                    h2{margin-top:0;color:#555;font-weight:normal;} 
                    #qrcode{margin:20px auto;}
                

        /* Better portrait layout on mobile */
        @media (max-width: 600px) {
            .file-row { flex-direction: column; align-items: stretch; }
            .file-info { width: 100%; white-space: normal; }
            .file-actions { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
            .action-btn { width: 40px; height: 40px; }
        }

        /* Preview Modal */
        .ppu-modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:99999; }
        .ppu-modal .inner { position:absolute; inset:0; display:flex; flex-direction:column; padding:14px; }
        .ppu-modal .topbar { display:flex; justify-content:space-between; align-items:center; color:#fff; margin-bottom:10px; }
        .ppu-modal .topbar button { background:rgba(255,255,255,0.15); color:#fff; border:0; border-radius:10px; padding:8px 12px; }
        .ppu-modal .viewer { flex:1; display:flex; align-items:center; justify-content:center; }
        .ppu-modal img { max-width:100%; max-height:100%; object-fit:contain; border-radius:12px; background:#111; }
        .ppu-modal .controls { display:flex; gap:10px; justify-content:center; margin-top:10px; }
        .ppu-modal .controls button { background:#fff; border:0; border-radius:12px; padding:10px 14px; font-size:16px; }
</style>
            </head>
            <body onload="window.print()">
                <div class="box">
                    <h1><?php echo esc_html($p['name']); ?></h1>
                    <h2>Scan for Bulletin</h2>
                    <div id="qrcode"></div>
                    <p><?php echo esc_html($url); ?></p>
                </div>
                <script>new QRCode(document.getElementById("qrcode"), {text: "<?php echo esc_js($url); ?>", width: 300, height: 300});</script>
            

<div id="ppuModal" class="ppu-modal" onclick="if(event.target===this) closePreview()">
  <div class="inner">
    <div class="topbar">
      <div id="ppuModalTitle" style="font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"></div>
      <button type="button" onclick="closePreview()">✕ Close</button>
    </div>
    <div class="viewer">
      <img id="ppuModalImg" alt="preview">
    </div>
    <div class="controls">
      <button type="button" onclick="rotatePreview(-90)"></button>
      <button type="button" onclick="rotatePreview(90)"></button>
    </div>
  </div>
</div>
</body></html>
            <?php 
            exit;
        }
        wp_die('Not found.', 'Not Found', ['response' => 404]);
    }
    
    // YEAR ZIP DOWNLOAD
    $zip_dio = ppu_safe_slug(get_query_var('ppu_zip_dio'));
    $zip_par = ppu_safe_slug(get_query_var('ppu_zip_par'));
    $zip_year = intval(get_query_var('ppu_zip_year'));
    if ($zip_dio && $zip_par && $zip_year) {
        ppu_handle_year_zip($zip_dio, $zip_par, $zip_year);
        exit;
    }

    // UPLOADER PAGE
    $up_dio = ppu_safe_slug(get_query_var('ppu_up_dio')); 
    $up_par = ppu_safe_slug(get_query_var('ppu_up_par'));
    
    if($up_dio && $up_par) {
        $parishes = ppu_get_parishes();
        $p_data = isset($parishes[$up_par]) ? $parishes[$up_par] : null;
        
        if (!$p_data || !is_array($p_data) || ($p_data['diocese'] ?? '') !== $up_dio) {
            wp_die('Parish not found.', 'Not Found', ['response' => 404]);
        }
        
        $server_key = $p_data['key'] ?? '';
        $client_key = $_GET['key'] ?? '';
        
        if(!hash_equals($server_key, (string)$client_key)) {
            // Log failed attempt
            ppu_log_upload($up_dio, $up_par, false);
            wp_die(
                '<h1>🔒 Invalid Link</h1>' .
                '<p>This upload link is invalid or has expired.</p>' .
                '<p>Please contact your parish administrator for a new link.</p>',
                'Access Denied', 
                ['response' => 403]
            );
        }
        
        nocache_headers();
        ppu_render_uploader($up_dio, $up_par, $server_key);
        exit;
    }
    
    // PUBLIC BULLETIN VIEWER
    $dio = ppu_safe_slug(get_query_var('ppu_dio')); 
    $par = ppu_safe_slug(get_query_var('ppu_par'));
    
    if($dio && $par) { 
        ppu_handle_redirect($dio, $par); 
        exit; 
    }
}
add_action('template_redirect', 'ppu_template_redirect');

// ============================================================================
// PUBLIC BULLETIN VIEWER (THE MISSING FUNCTION!)
// ============================================================================

function ppu_handle_redirect($dio, $par) {
    $store = ppu_resolve_parish_storage($dio, $par);
    $dir = $store['dir'];
    $base_url = $store['url'];
    if (!$dir || !$base_url) {
        wp_die('<h2>No bulletin available</h2><p>The weekly bulletin has not yet been uploaded.</p>', 'Not Found', ['response' => 404]);
    }

    $files = glob($dir . 'bulletin.*');
    if (empty($files)) {
        wp_die('<h2>No bulletin available</h2><p>The weekly bulletin has not yet been uploaded.</p>', 'Not Found', ['response' => 404]);
    }

    usort($files, function($a,$b){ return filemtime($b) <=> filemtime($a); });
    $file = $files[0];
    $mtime = @filemtime($file) ?: time();
    ppu_log_view($dio, $par);

    nocache_headers();
    wp_safe_redirect($base_url . basename($file) . '?t=' . $mtime);
    exit;
}


// ============================================================================
// REST API - FILE UPLOAD
// ============================================================================

function ppu_register_rest() {
    register_rest_route('ppu/v1', '/upload', [
        'methods' => 'POST',
        'permission_callback' => function($request) {
            $parishes = ppu_get_parishes();
            $parish = ppu_safe_slug($request['parish'] ?? '');
            
            if (!$parish) return false;
            
            $p_data = isset($parishes[$parish]) ? $parishes[$parish] : [];
            
            // Validate parish, diocese, and key
            $valid = (
                is_array($p_data) &&
                ($p_data['diocese'] ?? '') === ppu_safe_slug($request['diocese'] ?? '') &&
                hash_equals($p_data['key'] ?? '', (string)($request['key'] ?? ''))
            );
            
            if (!$valid) return false;
            
            // Check rate limit
            if (!ppu_check_rate_limit($parish, 'upload')) {
                return new WP_Error('rate_limit', 'Too many uploads. Please wait a minute.', ['status' => 429]);
            }
            
            return true;
        },
        'callback' => function($request) {
            $dio = ppu_safe_slug($request['diocese'] ?? ''); 
            $par = ppu_safe_slug($request['parish'] ?? '');
            
            if(!$dio || !$par) {
                return new WP_Error('invalid', 'Invalid parish data', ['status' => 400]);
            }
            
            // Ensure base directory exists
            $base_dir = realpath(PPU_DIR);
            if (!$base_dir) {
                wp_mkdir_p(PPU_DIR);
                $base_dir = realpath(PPU_DIR);
            }
            
            // Ensure parish directory exists
            $target_dir = untrailingslashit(ppu_parish_dir($dio, $par));
            if (!is_dir($target_dir)) {
                wp_mkdir_p($target_dir);
            }
            
            $real_target = realpath($target_dir);
            
            // Security: Path Traversal Check
            if(!$real_target || strpos($real_target, $base_dir) !== 0) {
                return new WP_Error('security', 'Path validation failed', ['status' => 403]);
            }
            
            if(!isset($_FILES['file']) || $_FILES['file']['error'] !== UPLOAD_ERR_OK) {
                $error_msg = isset($_FILES['file']) ? 'Upload error: ' . $_FILES['file']['error'] : 'No file received';
                return new WP_Error('upload', $error_msg, ['status' => 400]);
            }
            
            // Server-side file size check
            $settings = ppu_get_settings();
    // keep folders in sync
    ppu_ensure_storage_tree();
            $max_size = $settings['max_file_size_mb'] * 1024 * 1024;
            if ($_FILES['file']['size'] > $max_size) {
                return new WP_Error('size', 'File too large. Maximum: ' . $settings['max_file_size_mb'] . 'MB', ['status' => 413]);
            }
            
            // Security: Check MIME type
            $allowed_types = [
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'image/jpeg',
                'image/png'
            ];
            
            $file_type = mime_content_type($_FILES['file']['tmp_name']);
            if(!in_array($file_type, $allowed_types)) {
                return new WP_Error('type', 'File type not allowed: ' . $file_type, ['status' => 400]);
            }
            
            // Determine filename
            $ext = strtolower(pathinfo($_FILES['file']['name'], PATHINFO_EXTENSION));
            $allowed_ext = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'];
            if (!in_array($ext, $allowed_ext)) {
                return new WP_Error('ext', 'File extension not allowed', ['status' => 400]);
            }
            
            $filename = "bulletin." . $ext;
            $filepath = $real_target . '/' . $filename;
            
            // File locking for concurrent uploads
            $lock_file = $real_target . '/.lock';
            $lock = fopen($lock_file, 'w');
            if(!$lock || !flock($lock, LOCK_EX)) {
                return new WP_Error('busy', 'Server busy, please try again', ['status' => 503]);
            }
            
            try {
                // Archive previous bulletin (move into archive folder)
                $existing = glob($real_target . '/bulletin.*');
                if ($existing && !empty($existing)) {
                    usort($existing, function($a,$b){ return filemtime($b) <=> filemtime($a); });
                    $old_file = $existing[0];
                    $old_ts = @filemtime($old_file) ?: time();
                    $old_date = ppu_archive_get_last_sunday($dio, $par);
                    if (!$old_date) $old_date = ppu_guess_sunday_date_from_ts($old_ts);
                    ppu_archive_move_file($dio, $par, $old_file, $old_date);
                }

                // Store upcoming Sunday date for the NEW bulletin (Automatic)
                $new_date = ppu_upcoming_sunday_date();
                ppu_archive_store_last_sunday($dio, $par, $new_date);

                // Remove old bulletins
                foreach (glob($real_target . "/bulletin.*") as $old_file) { 
                    if(is_file($old_file)) @unlink($old_file); 
                }
                
                
                // Also remove any previous versioned bulletin files (bulletin-*.pdf/jpg/png) to avoid disk usage on shared hosting
                foreach (glob($real_target . "/bulletin-*.*") as $snap_file) {
                    if (is_file($snap_file)) {
                        @unlink($snap_file);
                    }
                }

// Move uploaded file
                if(!move_uploaded_file($_FILES['file']['tmp_name'], $filepath)) {
                    throw new Exception('Failed to save file');
                }
                
                // Log successful upload
                ppu_log_upload($dio, $par, true);
                
                flock($lock, LOCK_UN); 
                fclose($lock);
                
                return [
                    'status' => 'success', 
                    'file_url' => ppu_parish_url($dio, $par) . $filename . '?t=' . time(),
                    'message' => 'Bulletin published successfully'
                ];
                
            } catch(Exception $e) {
                flock($lock, LOCK_UN); 
                fclose($lock);
                ppu_log_upload($dio, $par, false);
                return new WP_Error('save', 'Save failed: ' . $e->getMessage(), ['status' => 500]);
            }
        }
    ]);
}
add_action('rest_api_init', 'ppu_register_rest');

// ============================================================================
// YEAR ZIP HANDLER
// ============================================================================
function ppu_build_year_zip($dio, $par, $year) {
    if (!class_exists('ZipArchive')) return ['ok' => false, 'error' => 'ZIP support not available on this server.'];

    $dio = ppu_safe_slug($dio);
    $par = ppu_safe_slug($par);
    $year = intval($year);
    if (!$dio || !$par || $year < 2000) return ['ok' => false, 'error' => 'Invalid request.'];

    $zip_dir = ppu_parish_archive_dir($dio, $par, $year);
    if (!$zip_dir) return ['ok' => false, 'error' => 'Archive folder not available.'];

    wp_mkdir_p($zip_dir);

    $zip_path = trailingslashit($zip_dir) . 'archive-' . $year . '.zip';
    $needs = !file_exists($zip_path);

    $latest = 0;
    $tree = ppu_archive_scan($dio, $par);
    if (isset($tree[strval($year)])) {
        foreach ($tree[strval($year)] as $m => $items) {
            foreach ($items as $it) {
                $latest = max($latest, @filemtime($it['file']) ?: 0);
            }
        }
    }

    // include current live file if last-sunday matches this year
    $last = ppu_archive_get_last_sunday($dio, $par);
    $store = ppu_resolve_parish_storage($dio, $par);
    $live = glob($store['dir'] . 'bulletin.*');
    if ($last && substr($last, 0, 4) == strval($year) && $live) {
        usort($live, function($a,$b){ return filemtime($b) <=> filemtime($a); });
        $latest = max($latest, @filemtime($live[0]) ?: 0);
    }

    if (!$needs && filemtime($zip_path) < $latest) $needs = true;

    if ($needs) {
        $zip = new ZipArchive();
        if ($zip->open($zip_path, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
            return ['ok' => false, 'error' => 'Could not create ZIP.'];
        }

        if (isset($tree[strval($year)])) {
            foreach ($tree[strval($year)] as $m => $items) {
                foreach ($items as $it) {
                    $zip->addFile($it['file'], basename($it['file']));
                }
            }
        }

        if ($last && substr($last, 0, 4) == strval($year) && $live) {
            $ext = strtolower(pathinfo($live[0], PATHINFO_EXTENSION));
            $zip->addFile($live[0], $last . '.' . $ext);
        }

        $zip->close();
    }

    return ['ok' => true, 'path' => $zip_path];
}

function ppu_stream_zip_file($zip_path) {
    nocache_headers();
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="' . basename($zip_path) . '"');
    header('Content-Length: ' . filesize($zip_path));
    readfile($zip_path);
    exit;
}

function ppu_handle_year_zip($dio, $par, $year) {
    $res = ppu_build_year_zip($dio, $par, $year);
    if (!$res['ok']) {
        wp_die('<h2>Archive not available</h2><p>' . esc_html($res['error']) . '</p>');
    }
    ppu_stream_zip_file($res['path']);
}

// ============================================================================
// ARCHIVE PAGES + SHORTCODE + ADMIN
// ============================================================================
function ppu_generate_archive_pages() {
    if (!current_user_can('manage_options')) return;
    $parishes = ppu_get_parishes();
    $pages = get_option('ppu_archive_pages', []);
    if (!is_array($pages)) $pages = [];

    foreach ($parishes as $p_slug => $p) {
        if (!is_array($p) || !isset($p['diocese'])) continue;
        $slug = $p_slug . '-archive';
        $title = ($p['name'] ?? ucfirst($p_slug)) . ' Archive';
        $content = '[ppu_archive diocese="' . esc_attr($p['diocese']) . '" parish="' . esc_attr($p_slug) . '"]';

        $existing = get_page_by_path($slug);
        if ($existing && $existing->ID) {
            wp_update_post(['ID' => $existing->ID, 'post_content' => $content, 'post_title' => $title, 'post_status' => 'publish']);
            $pages[$p_slug] = $existing->ID;
        } else {
            $id = wp_insert_post(['post_title' => $title, 'post_name' => $slug, 'post_content' => $content, 'post_status' => 'publish', 'post_type' => 'page']);
            if ($id && !is_wp_error($id)) $pages[$p_slug] = $id;
        }
    }

    update_option('ppu_archive_pages', $pages);
}

function ppu_archive_shortcode($atts = []) {
    $atts = shortcode_atts(['diocese' => '', 'parish' => '', 'title' => ''], $atts);
    $dio = ppu_safe_slug($atts['diocese']);
    $par = ppu_safe_slug($atts['parish']);
    if (!$dio || !$par) return '<p>Archive is not configured for this page.</p>';

    $parishes = ppu_get_parishes();
    $p_name = isset($parishes[$par]['name']) ? $parishes[$par]['name'] : $par;

    $tree  = ppu_archive_scan($dio, $par);
    $sizes = ppu_archive_calc_sizes($dio, $par);

    $drive_links = get_option('ppu_drive_links', []);
    $drive_years = [];
    if (is_array($drive_links) && isset($drive_links[$par]) && is_array($drive_links[$par])) {
        $drive_years = array_keys($drive_links[$par]);
    }

    $years = array_unique(array_merge(array_keys($tree), $drive_years));
    rsort($years);

    ob_start();
    ?>
    <div class="ppu-archive" style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:1100px">
      <style>
        .ppu-archive .btn{display:inline-block;padding:10px 14px;border-radius:10px;border:1px solid #cbd5e1;text-decoration:none;color:#111;background:#f8fafc;margin-right:8px;margin-top:6px}
        .ppu-archive .btn.primary{background:#0ea5e9;color:#fff;border-color:#0ea5e9}
        details{border:1px solid #e5e7eb;border-radius:12px;padding:10px 12px;margin:12px 0;background:#fff}
        summary{cursor:pointer;font-weight:600}
        .month{margin:10px 0 0 0;padding-left:10px}
        .item{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid #f1f5f9}
        .item:last-child{border-bottom:0}
        .muted{color:#64748b;font-size:13px}
        .pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#f1f5f9;color:#334155;font-size:12px;margin-left:8px}
        select.ppu-month-select{padding:8px 10px;border-radius:10px;border:1px solid #cbd5e1;background:#fff;margin-top:10px}
        .btn.small{padding:8px 12px;border-radius:10px;font-size:13px}
      </style>

      <h2><?php echo esc_html($atts['title'] ? $atts['title'] : ($p_name . ' Bulletin Archive')); ?></h2>

      <?php if (empty($years)): ?>
        <p>No archived bulletins yet.</p>
      <?php else: ?>
        <?php foreach ($years as $year):
              $year = intval($year);
              $months = isset($tree[strval($year)]) ? $tree[strval($year)] : [];
              $has_local = !empty($months);
              $drive = ppu_archive_get_drive_link($par, $year);
              $y_bytes = isset($sizes['years'][strval($year)]) ? intval($sizes['years'][strval($year)]) : 0;
              $month_keys = array_keys($months);
              rsort($month_keys);
              $default_month = $month_keys ? $month_keys[0] : '';
              $uid = 'ppu-' . $dio . '-' . $par . '-' . $year;
        ?>
          <details>
            <summary><?php echo esc_html($year); ?><?php if ($has_local): ?> <span class="pill"><?php echo esc_html(ppu_mb($y_bytes)); ?> MB</span><?php endif; ?></summary>

            <?php if (!$has_local && $drive): ?>
              <a class="btn primary" target="_blank" rel="noopener" href="<?php echo esc_url($drive); ?>">View on Google Drive</a>
            <?php elseif (!$has_local): ?>
              <p class="muted" style="margin-top:10px">No local files for this year yet.</p>
            <?php endif; ?>

            <?php if ($has_local): ?>
              <label class="muted" for="<?php echo esc_attr($uid); ?>-month">Month:</label>
              <select class="ppu-month-select" id="<?php echo esc_attr($uid); ?>-month">
                <option value="all">All months</option>
                <?php foreach ($month_keys as $mk): ?>
                  <option value="<?php echo esc_attr($mk); ?>" <?php echo ($mk === $default_month ? 'selected' : ''); ?>><?php echo esc_html(date('F Y', strtotime($mk . '-01'))); ?></option>
                <?php endforeach; ?>
              </select>

              <?php if ($drive): ?>
                <div style="margin-top:10px">
                  <a class="btn small" target="_blank" rel="noopener" href="<?php echo esc_url($drive); ?>">View on Google Drive</a>
                </div>
              <?php endif; ?>

              <div id="<?php echo esc_attr($uid); ?>-container">
                <?php foreach ($months as $month => $items): ?>
                  <div class="ppu-month" data-month="<?php echo esc_attr($month); ?>" style="display:none">
                    <div class="month">
                      <h4><?php echo esc_html(date('F Y', strtotime($month . '-01'))); ?></h4>
                      <?php foreach ($items as $it):
                            $ts = strtotime($it['date']);
                            $label = 'Sun ' . date('d M', $ts);
                            $y = date('Y', $ts);
                            $url = ppu_parish_archive_url($dio, $par, $y) . basename($it['file']);
                            $ext = strtolower($it['ext']);
                            $is_viewable = in_array($ext, ['pdf','jpg','jpeg','png']);
                      ?>
                        <div class="item">
                          <div><?php echo esc_html($label); ?> <span class="muted">(<?php echo esc_html(strtoupper($ext)); ?>)</span></div>
                          <div>
                            <?php if ($is_viewable): ?>
                              <a class="btn small" target="_blank" rel="noopener" href="<?php echo esc_url($url); ?>">View</a>
                              <a class="btn small" target="_blank" rel="noopener" href="<?php echo esc_url($url); ?>" download>Download</a>
                            <?php else: ?>
                              <a class="btn small" target="_blank" rel="noopener" href="<?php echo esc_url($url); ?>">Download</a>
                            <?php endif; ?>
                          </div>
                        </div>
                      <?php endforeach; ?>
                    </div>
                  </div>
                <?php endforeach; ?>
              </div>

              <script>
                (function(){
                  function show(uid, month){
                    var container = document.getElementById(uid+'-container');
                    if(!container) return;
                    var blocks = container.querySelectorAll('.ppu-month');
                    blocks.forEach(function(b){
                      if(month==='all'){ b.style.display='block'; }
                      else { b.style.display = (b.getAttribute('data-month')===month)?'block':'none'; }
                    });
                  }
                  var uid = '<?php echo esc_js($uid); ?>';
                  var sel = document.getElementById(uid+'-month');
                  if(sel){
                    show(uid, sel.value || '<?php echo esc_js($default_month); ?>');
                    sel.addEventListener('change', function(){ show(uid, this.value); });
                  }
                })();
              </script>
            <?php endif; ?>

          </details>
        <?php endforeach; ?>
      <?php endif; ?>
    </div>
    <?php
    return ob_get_clean();
}
add_shortcode('ppu_archive', 'ppu_archive_shortcode');

function ppu_archive_admin_page() {
    if (!current_user_can('manage_options')) wp_die('Unauthorized');

    $parishes = ppu_get_parishes();
    $message = '';

    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        check_admin_referer('ppu_archive_action');

        if (isset($_POST['ppu_generate_archive_pages']) && $_POST['ppu_generate_archive_pages'] === '1') {
            ppu_generate_archive_pages();
            $message = 'Archive pages generated/updated.';
        }

        if (isset($_POST['ppu_save_drive_link']) && $_POST['ppu_save_drive_link'] === '1') {
            $p_slug = ppu_safe_slug($_POST['drive_parish'] ?? '');
            $year = intval($_POST['drive_year'] ?? 0);
            $url = $_POST['drive_url'] ?? '';

            // Accept any HTTPS link; you can paste Google Drive folder links.
            $url_clean = esc_url_raw($url);

            if ($p_slug && $year && $url_clean) {
                ppu_archive_add_drive_link($p_slug, $year, $url_clean);
                $message = 'Drive link saved.';
            } else {
                $message = 'Drive link not saved (invalid parish/year/link).';
            }
        }

        if (isset($_POST['ppu_delete_local_year']) && $_POST['ppu_delete_local_year'] === '1') {
            $dio = ppu_safe_slug($_POST['del_dio'] ?? '');
            $par = ppu_safe_slug($_POST['del_par'] ?? '');
            $year = intval($_POST['del_year'] ?? 0);
            if ($dio && $par && $year) {
                $dir = ppu_parish_archive_dir($dio, $par, $year);
                if ($dir && is_dir($dir)) {
                    foreach (glob(trailingslashit($dir) . '*.*') as $f) { if (is_file($f)) @unlink($f); }
                    @rmdir($dir);
                }
                $message = 'Local archive deleted for ' . $year . '.';
            }
        }
    }

    $archive_pages = get_option('ppu_archive_pages', []);
    if (!is_array($archive_pages)) $archive_pages = [];

    echo '<div class="wrap"><h1>Parish Press – Archive</h1>';
    if ($message) echo '<div class="notice notice-success"><p>' . esc_html($message) . '</p></div>';

    echo '<form method="post" style="margin:12px 0">';
    wp_nonce_field('ppu_archive_action');
    echo '<input type="hidden" name="ppu_generate_archive_pages" value="1" />';
    echo '<button class="button button-primary">Generate / Update Archive Pages</button>';
    echo '</form>';

    echo '<table class="widefat striped"><thead><tr>';
    echo '<th>Parish</th><th>Archive Page</th><th>Archive Size (MB)</th><th>Year</th><th>Download ZIP</th><th>Drive Link</th><th>Save</th><th>Delete Local</th>';
    echo '</tr></thead><tbody>';

    foreach ($parishes as $pslug => $p) {
        if (!is_array($p) || !isset($p['diocese'])) continue;
        $dio = $p['diocese'];
        $sizes = ppu_archive_calc_sizes($dio, $pslug);
        $years = array_keys($sizes['years']);
        rsort($years);
        $year = $years ? intval($years[0]) : intval(date('Y'));

        $page_id = isset($archive_pages[$pslug]) ? intval($archive_pages[$pslug]) : 0;
        $page_link = $page_id ? get_permalink($page_id) : '';

        $zip_url = wp_nonce_url(admin_url('admin-post.php?action=ppu_admin_year_zip&dio=' . rawurlencode($dio) . '&par=' . rawurlencode($pslug) . '&year=' . intval($year)), 'ppu_admin_year_zip');

        echo '<tr>';
        echo '<td>' . esc_html($p['name'] ?? $pslug) . '</td>';
        echo '<td>' . ($page_link ? '<a target="_blank" rel="noopener" href="' . esc_url($page_link) . '">Open</a>' : '<span style="color:#b45309">Not created</span>') . '</td>';
        echo '<td>' . esc_html(ppu_mb($sizes['total_bytes'])) . '</td>';
        echo '<td>' . esc_html($year) . '</td>';
        echo '<td><a class="button" href="' . esc_url($zip_url) . '">Download</a></td>';

        echo '<td>';
        echo '<form method="post" style="display:flex;gap:6px;align-items:center">';
        wp_nonce_field('ppu_archive_action');
        echo '<input type="hidden" name="ppu_save_drive_link" value="1" />';
        echo '<input type="hidden" name="drive_parish" value="' . esc_attr($pslug) . '" />';
        echo '<input type="hidden" name="drive_year" value="' . esc_attr($year) . '" />';
        echo '<input type="url" name="drive_url" placeholder="Paste Google Drive link" value="' . esc_attr(ppu_archive_get_drive_link($pslug, $year)) . '" style="width:260px" />';
        echo '</td>';
        echo '<td><button class="button">Save</button></td>';
        echo '</form>';

        echo '<td>';
        echo '<form method="post" onsubmit="return confirm(\'Delete local archive for this year?\');">';
        wp_nonce_field('ppu_archive_action');
        echo '<input type="hidden" name="ppu_delete_local_year" value="1" />';
        echo '<input type="hidden" name="del_dio" value="' . esc_attr($dio) . '" />';
        echo '<input type="hidden" name="del_par" value="' . esc_attr($pslug) . '" />';
        echo '<input type="hidden" name="del_year" value="' . esc_attr($year) . '" />';
        echo '<button class="button">Delete</button>';
        echo '</form>';
        echo '</td>';

        echo '</tr>';
    }

    echo '</tbody></table>';
    echo '<p style="margin-top:10px;color:#64748b">Note: The plugin stores the Drive link only. Ensure the Drive folder/file is shared so your intended audience can view it.</p>';
    echo '</div>';
}

function ppu_admin_year_zip_handler() {
    if (!current_user_can('manage_options')) wp_die('Unauthorized');
    check_admin_referer('ppu_admin_year_zip');

    $dio = ppu_safe_slug($_GET['dio'] ?? '');
    $par = ppu_safe_slug($_GET['par'] ?? '');
    $year = intval($_GET['year'] ?? 0);
    if (!$dio || !$par || !$year) wp_die('Invalid request.');

    $res = ppu_build_year_zip($dio, $par, $year);
    if (!$res['ok']) wp_die('<h2>Archive not available</h2><p>' . esc_html($res['error']) . '</p>');
    ppu_stream_zip_file($res['path']);
}
add_action('admin_post_ppu_admin_year_zip', 'ppu_admin_year_zip_handler');

// ============================================================================
// ADMIN MENU
// ============================================================================

function ppu_menu() {
    add_menu_page('Parish Press', 'Parish Press', 'manage_options', 'ppu-dashboard', 'ppu_admin_ui', 'dashicons-groups', 30);
    add_submenu_page('ppu-dashboard', 'Archive', 'Archive', 'manage_options', 'ppu-archive', 'ppu_archive_admin_page');
}

add_action('admin_menu', 'ppu_menu');

function ppu_plugin_action_links($links) {
    $url = admin_url('admin.php?page=ppu-dashboard');
    array_unshift($links, '<a href="' . esc_url($url) . '">Settings</a>');
    return $links;
}
add_filter('plugin_action_links_' . plugin_basename(PPU_PLUGIN_FILE), 'ppu_plugin_action_links');

// ============================================================================
// ADMIN UI
// ============================================================================

function ppu_admin_ui() {
    if (!current_user_can('manage_options')) {
        wp_die('Unauthorized');
    }
    
    $areas = ppu_get_areas(); 
    $dioceses = ppu_get_dioceses(); 
    $parishes = ppu_get_parishes();
    $settings = ppu_get_settings();
    $active_tab = isset($_GET['tab']) ? sanitize_key($_GET['tab']) : 'parishes';
    $message = '';
    
    // --- POST Actions ---
        // Clear all dioceses (start empty). Safe: parishes set to unassigned; filesystem untouched.
        if (isset($_POST['ppu_clear_dioceses']) && $_POST['ppu_clear_dioceses'] === '1') {
            update_option('ppu_dioceses', []);
            foreach ($parishes as $pslug => $pdata) {
                if (is_array($pdata)) {
                    $parishes[$pslug]['diocese'] = 'unassigned';
                }
            }
            update_option('ppu_parishes', $parishes);
            $dioceses = [];
            $message = '<div class="notice notice-success is-dismissible"><p>Dioceses cleared.</p></div>';
            $active_tab = 'dioceses';
        }

    if ($_SERVER['REQUEST_METHOD'] === 'POST' && check_admin_referer('ppu_admin_action')) {
        
        // Settings Update
        if (isset($_POST['ppu_settings_update'])) {
            update_option('ppu_settings', [
                'max_file_size_mb' => max(1, min(100, intval($_POST['max_file_size_mb']))),
                'max_pages' => max(1, min(100, intval($_POST['max_pages'])))
            ]);
            $settings = ppu_get_settings(); 
            $message = '<div class="notice notice-success is-dismissible"><p>Settings updated.</p></div>'; 
            $active_tab = 'settings';
        }
        
        // Move Parish
        if (isset($_POST['move_parish_action']) && $_POST['move_parish_action'] === '1') {
            $p_slug = ppu_safe_slug($_POST['move_parish_slug'] ?? ''); 
            $new_d_slug = ppu_safe_slug($_POST['new_diocese_slug'] ?? '');
            
            if ($p_slug && $new_d_slug && isset($parishes[$p_slug]) && isset($dioceses[$new_d_slug])) {
                $old_d_slug = $parishes[$p_slug]['diocese'] ?? 'unknown';
                $old_store = ppu_resolve_parish_storage($old_d_slug, $p_slug);
                $old_dir = untrailingslashit($old_store['dir']);
                $new_dir = untrailingslashit(ppu_parish_dir($new_d_slug, $p_slug));
                
                // Ensure new area/diocese directory exists
                $new_area = ppu_get_diocese_area_slug($new_d_slug);
                if (!is_dir(PPU_DIR . $new_area . '/' . $new_d_slug)) {
                    wp_mkdir_p(PPU_DIR . $new_area . '/' . $new_d_slug);
                }
                
                if (is_dir($old_dir)) {
                    if (@rename($old_dir, $new_dir)) {
                        $message = '<div class="notice notice-success is-dismissible"><p>Parish moved successfully.</p></div>';
                    } else {
                        $message = '<div class="notice notice-warning is-dismissible"><p><strong>Warning:</strong> Could not move folder. Please manually move via FTP.</p></div>';
                    }
                }

                $parishes[$p_slug]['diocese'] = $new_d_slug; 
                update_option('ppu_parishes', $parishes);
            }
        }
        
        // Reset Key
        if (isset($_POST['reset_key_action']) && $_POST['reset_key_action'] === '1') {
            $p_slug = ppu_safe_slug($_POST['reset_key_slug'] ?? '');
            if ($p_slug && isset($parishes[$p_slug])) {
                $parishes[$p_slug]['key'] = bin2hex(random_bytes(16)); 
                update_option('ppu_parishes', $parishes);
                $message = '<div class="notice notice-success is-dismissible"><p>Security key reset. Old links will no longer work.</p></div>';
            }
        }
        
        // Delete Parish
        if (isset($_POST['del_parish_action']) && $_POST['del_parish_action'] === '1') {
            $slug = ppu_safe_slug($_POST['del_parish_slug'] ?? '');
            if($slug && isset($parishes[$slug])) { 
                $dir_slug = $parishes[$slug]['diocese'] ?? 'unknown';
                $dir = ppu_parish_dir($dir_slug, $slug);
                
                // Delete all files in directory
                if (is_dir($dir)) {
                    array_map('unlink', glob("$dir*")); 
                    @rmdir($dir);
                }
                
                unset($parishes[$slug]); 
                update_option('ppu_parishes', $parishes);
                $message = '<div class="notice notice-success is-dismissible"><p>Parish deleted.</p></div>';
            }
        }

        // Add Area
        if (isset($_POST['new_area_name']) && !empty($_POST['new_area_name'])) {
            $slug = sanitize_title($_POST['new_area_name']);
            if ($slug && !isset($areas[$slug])) { 
                $areas[$slug] = sanitize_text_field($_POST['new_area_name']); 
                update_option('ppu_areas', $areas);
                // Ensure area folder exists
                wp_mkdir_p(PPU_DIR . $slug);
                $message = '<div class="notice notice-success is-dismissible"><p>Area added.</p></div>';
            }
            $active_tab = 'areas';
        }
        
        // Delete Area
        if (isset($_POST['del_area'])) {
            $slug = sanitize_key($_POST['del_area']); 
            if($slug !== 'unassigned') { 
                unset($areas[$slug]); 
                update_option('ppu_areas', $areas);
                // Ensure area folder exists
                wp_mkdir_p(PPU_DIR . $slug);
            }
            $active_tab = 'areas';
        }
        
        // Add Diocese
        if (isset($_POST['new_diocese_name']) && !empty($_POST['new_diocese_name'])) {
            $slug = sanitize_title($_POST['new_diocese_name']);
            if ($slug && !isset($dioceses[$slug])) {
                $dioceses[$slug] = [
                    'name' => sanitize_text_field($_POST['new_diocese_name']), 
                    'area' => sanitize_key($_POST['target_area'] ?? 'unassigned')
                ]; 
                update_option('ppu_dioceses', $dioceses);
                // Ensure area/diocese folder exists
                $area_slug = sanitize_key($dioceses[$slug]['area'] ?? 'unassigned');
                if (!$area_slug) $area_slug = 'unassigned';
                wp_mkdir_p(PPU_DIR . $area_slug . '/' . $slug);
                $message = '<div class="notice notice-success is-dismissible"><p>Diocese added.</p></div>';
            }
            $active_tab = 'dioceses';
        }
        
        // Delete Diocese
        if (isset($_POST['del_diocese_slug'])) {
            $slug = ppu_safe_slug($_POST['del_diocese_slug']); 
            if($slug) { 
                unset($dioceses[$slug]); 
                update_option('ppu_dioceses', $dioceses);
                // Ensure area/diocese folder exists
                $area_slug = sanitize_key($dioceses[$slug]['area'] ?? 'unassigned');
                if (!$area_slug) $area_slug = 'unassigned';
                wp_mkdir_p(PPU_DIR . $area_slug . '/' . $slug);
            }
            $active_tab = 'dioceses';
        }
        
        // Add Parish
        if (isset($_POST['new_parish_name']) && isset($_POST['target_diocese']) && !empty($_POST['new_parish_name'])) {
            $p_slug = sanitize_title($_POST['new_parish_name']);
            $d_slug = ppu_safe_slug($_POST['target_diocese']);
            if ($p_slug && $d_slug && !isset($parishes[$p_slug])) {
                $parishes[$p_slug] = [
                    'name' => sanitize_text_field($_POST['new_parish_name']), 
                    'diocese' => $d_slug, 
                    'key' => bin2hex(random_bytes(16))
                ];
                update_option('ppu_parishes', $parishes); 
                wp_mkdir_p(ppu_parish_dir($d_slug, $p_slug));
                $message = '<div class="notice notice-success is-dismissible"><p>Parish created.</p></div>';
            }
        }
        
        // Refresh data after changes
            $areas = ppu_get_areas();
            $dioceses = ppu_get_dioceses();
            $parishes = ppu_get_parishes();
            ppu_ensure_storage_tree($areas, $dioceses, $parishes);
    }

    // --- Render Admin Page ---
    ?>
    <div class="wrap">
        <h1 style="margin-bottom:20px;">
            <span class="dashicons dashicons-groups" style="font-size:30px;margin-right:10px;"></span>
            Parish Press Manager
        </h1>
        
        <?php echo $message; ?>
        
        <h2 class="nav-tab-wrapper">
            <a href="?page=ppu-dashboard&tab=parishes" class="nav-tab <?php echo $active_tab=='parishes' ? 'nav-tab-active' : ''; ?>">
                📍 Parishes
            </a>
            <a href="?page=ppu-dashboard&tab=dioceses" class="nav-tab <?php echo $active_tab=='dioceses' ? 'nav-tab-active' : ''; ?>">
                ⛪ Dioceses
            </a>
            <a href="?page=ppu-dashboard&tab=areas" class="nav-tab <?php echo $active_tab=='areas' ? 'nav-tab-active' : ''; ?>">
                🗺️ Areas
            </a>
            <a href="?page=ppu-dashboard&tab=settings" class="nav-tab <?php echo $active_tab=='settings' ? 'nav-tab-active' : ''; ?>">
                ⚙️ Settings
            </a>
        </h2>

        <?php if ($active_tab === 'settings'): ?>
        
            <div class="card" style="max-width:500px;margin-top:20px;padding:20px;">
                <form method="post">
                    <?php wp_nonce_field('ppu_admin_action'); ?>
                    <input type="hidden" name="ppu_settings_update" value="1">
                    
                    <h3 style="margin-top:0;">Upload Limits</h3>
                    
                    <p>
                        <label><strong>Max File Size (MB):</strong><br>
                        <input type="number" name="max_file_size_mb" value="<?php echo esc_attr($settings['max_file_size_mb']); ?>" min="1" max="100" class="regular-text">
                        </label>
                    </p>
                    
                    <p>
                        <label><strong>Max Pages (PDF/Images):</strong><br>
                        <input type="number" name="max_pages" value="<?php echo esc_attr($settings['max_pages']); ?>" min="1" max="100" class="regular-text">
                        </label>
                    </p>
                    
                    <button class="button button-primary">Save Changes</button>
                </form>
            </div>
            
            <div class="card" style="max-width:500px;margin-top:20px;padding:20px;">
                <h3 style="margin-top:0;">Security Information</h3>
                <p>This plugin uses <strong>secure shareable links</strong> for uploads - no passwords required.</p>
                <ul style="list-style:disc;margin-left:20px;">
                    <li>Each parish has a unique 32-character security key</li>
                    <li>Only people with the link can upload</li>
                    <li>Reset a key if you suspect it's been shared inappropriately</li>
                    <li>Uploads are rate-limited to prevent abuse</li>
                </ul>
            </div>
            
        <?php elseif ($active_tab === 'areas'): ?>
        
            <br>
            <form method="post" style="display:flex;gap:10px;">
                <?php wp_nonce_field('ppu_admin_action'); ?>
                <input type="text" name="new_area_name" placeholder="New Area Name" required>
                <button class="button button-primary">Add Area</button>
            </form>
            
            <table class="wp-list-table widefat fixed striped" style="margin-top:15px;max-width:600px;">
                <thead>
                    <tr><th>Name</th><th style="width:100px;">Actions</th></tr>
                </thead>
                <tbody>
                <?php foreach($areas as $slug => $name): ?>
                    <tr>
                        <td><?php echo esc_html($name); ?></td>
                        <td>
                            <?php if($slug !== 'unassigned'): ?>
                            <form method="post" onsubmit="return confirm('Delete this area?')">
                                <?php wp_nonce_field('ppu_admin_action'); ?>
                                <input type="hidden" name="del_area" value="<?php echo esc_attr($slug); ?>">
                                <button class="button button-small button-link-delete">Delete</button>
                            </form>
                            <?php else: ?>
                            <em style="color:#999;">Default</em>
                            <?php endif; ?>
                        </td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
            
        <?php elseif ($active_tab === 'dioceses'): ?>
        
            <br>
            <form method="post" style="display:flex;gap:10px;flex-wrap:wrap;">
                <?php wp_nonce_field('ppu_admin_action'); ?>
                <input type="text" name="new_diocese_name" placeholder="New Diocese Name" required>
                <select name="target_area">
                    <?php foreach($areas as $s => $n): ?>
                    <option value="<?php echo esc_attr($s); ?>"><?php echo esc_html($n); ?></option>
                    <?php endforeach; ?>
                </select>
                <button class="button button-primary">Add Diocese</button>
            </form>
            <form method="post" style="margin-top:10px;">
                <?php wp_nonce_field('ppu_admin_action'); ?>
                <input type="hidden" name="ppu_clear_dioceses" value="1">
                <button class="button button-secondary" onclick="return confirm('Clear ALL dioceses? Existing parishes will be set to Unassigned.');">Clear All Dioceses</button>
            </form>

            
            <table class="wp-list-table widefat fixed striped" style="margin-top:15px;">
                <thead>
                    <tr><th>Diocese</th><th>Area</th><th style="width:100px;">Actions</th></tr>
                </thead>
                <tbody>
                <?php 
                uasort($dioceses, function($a, $b) { 
                    return strcmp($a['name'] ?? '', $b['name'] ?? ''); 
                });
                foreach($dioceses as $slug => $d): 
                    if (!is_array($d) || !isset($d['name'])) continue;
                    $area_name = isset($areas[$d['area'] ?? '']) ? $areas[$d['area']] : 'N/A';
                ?>
                    <tr>
                        <td><strong><?php echo esc_html($d['name']); ?></strong></td>
                        <td><?php echo esc_html($area_name); ?></td>
                        <td>
                            <form method="post" onsubmit="return confirm('Delete this diocese? Parishes will need to be reassigned.')">
                                <?php wp_nonce_field('ppu_admin_action'); ?>
                                <input type="hidden" name="del_diocese_slug" value="<?php echo esc_attr($slug); ?>">
                                <button class="button button-small button-link-delete">Delete</button>
                            </form>
                        </td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
            
        <?php else: ?>
        
            <!-- PARISHES TAB -->
            <div style="background:#fff;border:1px solid #ccd0d4;padding:15px;margin-top:20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                <strong>Add New Parish:</strong>
                <form method="post" style="display:flex;gap:5px;flex-grow:1;flex-wrap:wrap;">
                    <?php wp_nonce_field('ppu_admin_action'); ?>
                    <input type="text" name="new_parish_name" placeholder="Parish Name" required style="width:250px;">
                    <select name="target_diocese" style="max-width:200px;">
                        <?php 
                        uasort($dioceses, function($a, $b) { 
                            return strcmp($a['name'] ?? '', $b['name'] ?? ''); 
                        });
                        foreach($dioceses as $s => $d): 
                            if (isset($d['name'])): 
                        ?>
                        <option value="<?php echo esc_attr($s); ?>"><?php echo esc_html($d['name']); ?></option>
                        <?php endif; endforeach; ?>
                    </select>
                    <button class="button button-primary">Create Parish</button>
                </form>
            </div>

            <div style="margin:15px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                <input type="text" id="ppu-search" placeholder="Search parishes..." style="padding:8px;width:300px;">
                <select id="ppu-filter-dio" onchange="filterTable()">
                    <option value="">All Dioceses</option>
                    <?php foreach($dioceses as $s => $d): if (isset($d['name'])): ?>
                    <option value="<?php echo esc_attr($d['name']); ?>"><?php echo esc_html($d['name']); ?></option>
                    <?php endif; endforeach; ?>
                </select>
                <span style="color:#666;font-size:13px;">
                    Total: <strong><?php echo count($parishes); ?></strong> parishes
                </span>
            </div>

            <table class="wp-list-table widefat fixed striped" id="ppu-table">
                <thead>
                    <tr>
                        <th style="width:20%;">Parish</th>
                        <th style="width:15%;">Diocese</th>
                        <th style="width:35%;">Uploader Link</th>
                        <th style="width:10%;text-align:center;">Views<br>(W/M/Y)</th>
                        <th style="width:20%;">Actions</th>
                    </tr>
                </thead>
                <tbody>
                <?php 
                uasort($parishes, function($a, $b) { 
                    return strcmp($a['name'] ?? '', $b['name'] ?? ''); 
                });
                
                foreach($parishes as $p_slug => $p): 
                    if (!is_array($p) || !isset($p['name'], $p['diocese'], $p['key'])) continue;
                    
                    $d_slug = $p['diocese']; 
                    $d_name = isset($dioceses[$d_slug]['name']) ? $dioceses[$d_slug]['name'] : 'Unknown';
                    $stats = ppu_get_stats($d_slug, $p_slug);
                    $upload_url = site_url("bulletin-upload/$d_slug/$p_slug?key={$p['key']}");
                    $view_url = site_url("bulletin/$d_slug/$p_slug");
                ?>
                    <tr class="ppu-row" data-name="<?php echo esc_attr(strtolower($p['name'])); ?>" data-dio="<?php echo esc_attr($d_name); ?>">
                        <td><strong><?php echo esc_html($p['name']); ?></strong></td>
                        <td><?php echo esc_html($d_name); ?></td>
                        <td>
                            <a href="<?php echo esc_url($upload_url); ?>" target="_blank" 
                               style="display:inline-block;max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:#0073aa;">
                                <?php echo esc_html($p['name']); ?> Uploader
                            </a>
                            <button type="button" class="button button-small" 
                                    onclick="copyToClipboard('<?php echo esc_js($upload_url); ?>', this)" 
                                    title="Copy Link">
                                <span class="dashicons dashicons-clipboard" style="font-size:14px;width:14px;height:14px;"></span>
                            </button>
                        </td>
                        <td style="text-align:center;font-size:12px;">
                            <?php echo "{$stats['w']} / {$stats['m']} / {$stats['y']}"; ?>
                        </td>
                        <td>
                            <div style="display:flex;gap:4px;flex-wrap:wrap;">
                                <a href="<?php echo esc_url($view_url); ?>" target="_blank" class="button button-small" title="View Bulletin">
                                    <span class="dashicons dashicons-visibility" style="margin-top:3px;"></span>
                                </a>
                                <a href="<?php echo esc_url(site_url("?ppu_qr=$p_slug")); ?>" target="_blank" class="button button-small" title="Print QR">
                                    <span class="dashicons dashicons-grid-view" style="margin-top:3px;"></span>
                                </a>
                                <button type="button" class="button button-small" onclick="toggleAdmin('<?php echo esc_js($p_slug); ?>')" title="Manage">
                                    <span class="dashicons dashicons-admin-generic" style="margin-top:3px;"></span>
                                </button>
                            </div>
                            
                            <!-- Hidden Admin Panel -->
                            <div id="adm-<?php echo esc_attr($p_slug); ?>" style="display:none;margin-top:10px;background:#f9f9f9;border:1px solid #ddd;padding:15px;text-align:left;">
                                <h4 style="margin:0 0 15px 0;border-bottom:1px solid #eee;padding-bottom:8px;">
                                    Manage: <?php echo esc_html($p['name']); ?>
                                </h4>
                                
                                <!-- Move Parish -->
                                <form method="post" onsubmit="return confirm('Move this parish to a different diocese?')" style="margin-bottom:15px;">
                                    <?php wp_nonce_field('ppu_admin_action'); ?>
                                    <input type="hidden" name="move_parish_slug" value="<?php echo esc_attr($p_slug); ?>">
                                    <input type="hidden" name="move_parish_action" value="1">
                                    <label>Move to Diocese:</label><br>
                                    <select name="new_diocese_slug" style="margin:5px 0;">
                                        <?php foreach($dioceses as $s => $d): if (isset($d['name'])): ?>
                                        <option value="<?php echo esc_attr($s); ?>" <?php selected($s, $d_slug); ?>>
                                            <?php echo esc_html($d['name']); ?>
                                        </option>
                                        <?php endif; endforeach; ?>
                                    </select>
                                    <button class="button button-small">Move</button>
                                </form>
                                
                                <!-- Reset Key -->
                                <form method="post" onsubmit="return confirm('Reset security key? The current upload link will stop working.')" style="margin-bottom:15px;">
                                    <?php wp_nonce_field('ppu_admin_action'); ?>
                                    <input type="hidden" name="reset_key_slug" value="<?php echo esc_attr($p_slug); ?>">
                                    <input type="hidden" name="reset_key_action" value="1">
                                    <button class="button button-small">🔑 Reset Upload Link</button>
                                    <span style="color:#666;font-size:12px;display:block;margin-top:5px;">
                                        Use if the link was shared with wrong people
                                    </span>
                                </form>
                                
                                <!-- Delete Parish -->
                                <form method="post" onsubmit="return confirm('PERMANENTLY DELETE this parish and all its files?')">
                                    <?php wp_nonce_field('ppu_admin_action'); ?>
                                    <input type="hidden" name="del_parish_slug" value="<?php echo esc_attr($p_slug); ?>">
                                    <input type="hidden" name="del_parish_action" value="1">
                                    <button class="button button-small button-link-delete">🗑️ Delete Parish</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
            
        <?php endif; ?>
    </div>
    
    <script>
    function filterTable() {
        var q = document.getElementById('ppu-search').value.toLowerCase();
        var d = document.getElementById('ppu-filter-dio').value;
        document.querySelectorAll('.ppu-row').forEach(function(r) {
            var name = r.dataset.name || '';
            var dio = r.dataset.dio || '';
            var show = name.includes(q) && (!d || dio === d);
            r.style.display = show ? 'table-row' : 'none';
        });
    }
    document.getElementById('ppu-search').addEventListener('keyup', filterTable);
    
    function toggleAdmin(slug) { 
        var el = document.getElementById('adm-' + slug); 
        el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }

    function copyToClipboard(text, button) {
        navigator.clipboard.writeText(text).then(function() {
            var original = button.innerHTML;
            button.innerHTML = '<span class="dashicons dashicons-yes" style="color:#46b450;font-size:14px;width:14px;height:14px;"></span>';
            setTimeout(function() { button.innerHTML = original; }, 1500);
        }).catch(function() {
            prompt('Copy this link:', text);
        });
    }
    </script>
    
    <style>
        #ppu-table td { vertical-align: middle; }
        .button .dashicons { vertical-align: middle; }
    </style>
    <?php
}

// ============================================================================
// UPLOADER UI (PWA)
// ============================================================================

function ppu_render_uploader($dio, $par, $key) {
    $parishes = ppu_get_parishes(); 
    $p_name = isset($parishes[$par]['name']) ? $parishes[$par]['name'] : 'Parish Bulletin';
    $dir = ppu_resolve_parish_storage($dio, $par)['dir']; 
    $is_mobile = wp_is_mobile();
    $settings = ppu_get_settings();
    
    // Check for active bulletin
    $active_html = '<em style="color:#888;">No active bulletin uploaded yet.</em>';
    $active_files = glob("$dir/bulletin.*");
    if ($active_files && !empty($active_files)) {
        $store = ppu_resolve_parish_storage($dio, $par);
        $url = $store['url'] . basename($active_files[0]) . '?t=' . filemtime($active_files[0]);
        $active_html = '<a href="' . esc_url($url) . '" target="_blank" style="color:#46b450;font-weight:bold;text-decoration:none;">✅ View Current Bulletin</a>'
            . ' <button type="button" style="margin-left:10px; padding:4px 10px; border-radius:10px; border:1px solid #c3c4c7; background:#fff; cursor:pointer;" onclick="(function(){var u=new URL(window.location.href);u.searchParams.set(&quot;ppu_refresh&quot;,Date.now());window.location.href=u.toString();})();" title="Refresh this page"></button>';
    }
    
    
    // View stats (Total)
    $v = ppu_get_stats($dio, $par);
    $views_html = '<div style="margin:10px 0 0; padding:10px; background:#f6f7f7; border:1px solid #dcdcde; border-radius:10px; font-size:14px;">'
        . '<strong>Views</strong>: '
        . '<span style="font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">'
        . 'Wk '.esc_html(date('W')).': '.esc_html($v['w'])
        . ' &nbsp;|&nbsp; '.esc_html(date('M')).': '.esc_html($v['m'])
        . ' &nbsp;|&nbsp; '.esc_html(date('Y')).': '.esc_html($v['y'])
        . '</span></div>';
$manifest_url = add_query_arg([
        'ppu_manifest' => '1', 
        'name' => urlencode($p_name),
        'start' => urlencode(site_url("bulletin-upload/$dio/$par?key=$key"))
    ], site_url('/'));
    
    $sw_url = add_query_arg(['ppu_sw' => '1'], site_url('/'));
    $current_url = site_url("bulletin-upload/$dio/$par?key=$key");

    // Desktop shortcuts (Windows .url and Mac .webloc)
    $win_shortcut = "[InternetShortcut]\r\nURL={$current_url}\r\n";
    $win_shortcut_data = 'data:application/octet-stream;base64,' . base64_encode($win_shortcut);

    $mac_shortcut = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n<plist version=\"1.0\">\n<dict>\n<key>URL</key>\n<string>{$current_url}</string>\n</dict>\n</plist>\n";
    $mac_shortcut_data = 'data:application/octet-stream;base64,' . base64_encode($mac_shortcut);
    ?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#0073aa">
    <link rel="manifest" href="<?php echo esc_url($manifest_url); ?>">
    <link rel="apple-touch-icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'%3E%3Crect fill='%230073aa' width='512' height='512' rx='64'/%3E%3Cpath fill='%23fff' d='M256 96L128 192v192h80V288h96v96h80V192L256 96z'/%3E%3C/svg%3E">
    <title>Upload: <?php echo esc_html($p_name); ?></title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background: #f0f2f5; padding: 15px; margin: 0; padding-bottom: 100px;
        }
        .box { 
            max-width: 500px; margin: 10px auto; background: #fff; 
            padding: 25px; border-radius: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }
        h1 { margin: 0 0 5px 0; font-size: 24px; text-align: center; }
        .subtitle { text-align: center; color: #666; margin-bottom: 20px; font-size: 14px; }
        .status-box { 
            background: #f8f9fa; border: 1px solid #e1e4e8; 
            padding: 15px; margin-bottom: 20px; font-size: 14px; 
            border-radius: 10px; text-align: center;
        }
        .action-grid { 
            display: grid; 
            grid-template-columns: <?php echo $is_mobile ? '1fr 1fr' : '1fr'; ?>; 
            gap: 12px; margin-bottom: 20px; 
        }
        .big-btn { 
            padding: 30px 15px; border: 2px dashed #ccc; border-radius: 12px; 
            background: #fafafa; cursor: pointer; text-align: center; 
            font-weight: 600; color: #555; display: flex; flex-direction: column; 
            align-items: center; justify-content: center; gap: 10px;
            transition: all 0.2s;
        }
        .big-btn:hover { border-color: #0073aa; background: #f0f7fc; }
        .big-btn.primary { 
            border-style: solid; background: #e8f4fc; 
            border-color: #0073aa; color: #0073aa; 
        }
        .big-btn svg { width: 36px; height: 36px; fill: currentColor; }
        .mobile-only { display: flex !important; }
        
        .btn { 
            width: 100%; padding: 18px; background: #0073aa; color: #fff; 
            border: none; cursor: pointer; font-size: 18px; border-radius: 12px; 
            font-weight: 600; margin-top: 15px; transition: background 0.2s;
        }
        .btn:hover { background: #005a87; }
        .btn:disabled { background: #ccc; cursor: not-allowed; }
        
        .file-list { margin-bottom: 15px; }
        .file-row { 
            display: flex; justify-content: space-between; padding: 12px; 
            background: #f9f9f9; border-radius: 10px; margin-bottom: 8px; 
            align-items: center; flex-wrap: wrap; gap: 10px;
        }
        .file-info { 
            flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; 
            font-size: 14px; font-weight: 500; display: flex; align-items: center; 
            min-width: 0;
        }
        .thumb { 
            width: 60px; height: 60px; object-fit: contain; border-radius: 6px; 
            margin-right: 12px; background: #eee; border: 1px solid #ddd;
            flex-shrink: 0;
        }
        
        .pdf-thumb {
            display: flex; align-items: center; justify-content: center;
            font-size: 26px; color: #555;
        }
        .desktop-only { display: none; }
.file-actions { display: flex; gap: 6px; }
        .action-btn { 
            width: 36px; height: 36px; border: 1px solid #ddd; background: #fff; 
            border-radius: 8px; font-size: 16px; cursor: pointer; 
            display: flex; align-items: center; justify-content: center;
            transition: all 0.2s;
        }
        .action-btn:hover { background: #f0f0f0; }
        .action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .del-btn { color: #d63638; border-color: #f5c6cb; }
        .del-btn:hover { background: #fef1f1; }
        .rot-btn { color: #0073aa; font-weight: bold; }
        
        .msg { 
            padding: 18px; margin-top: 20px; border-radius: 10px; 
            display: none; text-align: center; line-height: 1.6; font-size: 15px;
        }
        .err { background: #fef1f1; color: #8b0000; border: 1px solid #f5c6cb; }
        .suc { background: #ecf7ed; color: #155724; border: 1px solid #c3e6cb; }
        
        .footer-links { 
            margin-top: 25px; border-top: 1px solid #eee; padding-top: 20px; 
            text-align: center;
        }
        .footer-links button, .footer-links a { 
            display: inline-block; color: #666; text-decoration: none; 
            cursor: pointer; background: none; border: none; font-size: 13px;
            padding: 8px 15px; margin: 5px;
        }
        .footer-links button:hover, .footer-links a:hover { color: #0073aa; }
        
        #pwa-install-btn { 
            display: none; background: #46b450; color: white; width: 100%; 
            padding: 14px; border-radius: 10px; border: none; font-weight: 600; 
            margin-top: 12px; cursor: pointer; font-size: 16px;
        }
        #pwa-install-btn:hover { background: #3a9340; }
        
        .install-banner { 
            position: fixed; bottom: 0; left: 0; right: 0; background: #333; 
            color: white; padding: 20px; display: none; z-index: 9999; 
            box-shadow: 0 -4px 20px rgba(0,0,0,0.3); font-size: 15px; text-align: center;
        }
        .install-banner .close { 
            position: absolute; top: 12px; right: 15px; font-size: 24px; 
            color: #aaa; cursor: pointer; line-height: 1;
        }
        .install-banner .close:hover { color: #fff; }
        .ios-share-icon { 
            display: inline-block; width: 20px; height: 20px; 
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white"><path d="M12 2l-6 6h4v8h4v-8h4l-6-6zM5 14v6h14v-6h2v8H3v-8h2z"/></svg>') no-repeat center/contain; 
            vertical-align: bottom; margin: 0 4px;
        }
        
        .empty-state { 
            text-align: center; color: #888; font-style: italic; 
            padding: 30px; background: #fafafa; border-radius: 10px;
            border: 2px dashed #ddd;
        }
        
        
        @media (max-width: 600px) {
            .thumb { width: 80px; height: 80px; }
        }

@media (min-width: 900px) { 
            .desktop-only { display: block !important; }
            .mobile-only { display: none !important; } 
            .action-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>

<div class="box">
    <h1>📤 <?php echo esc_html($p_name); ?></h1>
    <p class="subtitle">Upload your weekly bulletin</p>
    
    <div class="status-box"><?php echo $active_html; echo $views_html; ?></div>

    <div class="desktop-only" style="margin: 14px 0 6px; font-size: 14px;">
        <strong>Add this uploader to your Desktop:</strong><br>
        <a href="<?php echo esc_attr($win_shortcut_data); ?>" download="<?php echo esc_attr($p_name); ?> Uploader.url" style="margin-right:12px;">
            🖥️ Download Windows Shortcut
        </a>
        <a href="<?php echo esc_attr($mac_shortcut_data); ?>" download="<?php echo esc_attr($p_name); ?> Uploader.webloc">
            🍏 Download Mac Shortcut
        </a>
    </div>

    
    <input type="file" id="f_file" multiple accept=".pdf,.doc,.docx" style="display:none">
    <input type="file" id="f_cam" accept="image/*" capture="environment" style="display:none">
    <input type="file" id="f_gallery" multiple accept="image/*" style="display:none">
    
    <div class="action-grid">
        <div class="big-btn primary mobile-only" onclick="document.getElementById('f_cam').click()">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.2"/><path d="M9 2L7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z"/></svg>
            <span>Take Photo</span>
        </div>
        <div class="big-btn mobile-only" onclick="document.getElementById('f_gallery').click()">
            <svg viewBox="0 0 24 24"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>
            <span>Choose Photos</span>
        </div>
        <div class="big-btn" onclick="document.getElementById('f_file').click()">
            <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>
            <span>Select Files</span>
        </div>
    </div>
    
    <div id="file-list" class="file-list"></div>
    
    <button id="upload-btn" class="btn" onclick="upload()">📤 Upload Bulletin</button>
    
    <div id="msg" class="msg"></div>
    
    <div class="footer-links">
        <button onclick="location.reload()">🔄 Start Over</button>
        <button id="pwa-install-btn">📲 Install App</button>
    </div>
</div>

<div id="install-banner" class="install-banner">
    <span class="close" onclick="this.parentElement.style.display='none'">&times;</span>
    <div id="ios-msg" style="display:none">
        <strong>Add to Home Screen:</strong><br>
        Tap <span class="ios-share-icon"></span> then "Add to Home Screen"
    </div>
    <div id="android-msg" style="display:none">
        <strong>Install App:</strong><br>
        Tap menu (⋮) → "Add to Home screen"
    </div>
</div>

<script>
// Register Service Worker for PWA
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('<?php echo esc_js($sw_url); ?>', { scope: '/bulletin-upload/' })
        .then(function(reg) { console.log('SW registered'); })
        .catch(function(err) { console.log('SW failed:', err); });
}

(function() {
    'use strict';
    
    // PWA Install handling
    let deferredPrompt;
    const installBtn = document.getElementById('pwa-install-btn');
    const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    const isAndroid = /Android/.test(navigator.userAgent);
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;

    window.addEventListener('beforeinstallprompt', function(e) {
        e.preventDefault();
        deferredPrompt = e;
        if (!isStandalone) installBtn.style.display = 'block';
    });

    installBtn.addEventListener('click', function() {
        if (deferredPrompt) {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then(function() { 
                deferredPrompt = null; 
                installBtn.style.display = 'none'; 
            });
        }
    });

    // Show install instructions for iOS/Android
    if (!isStandalone) {
        if (isIos) {
            document.getElementById('install-banner').style.display = 'block';
            document.getElementById('ios-msg').style.display = 'block';
        } else if (isAndroid) {
            setTimeout(function() {
                if (!deferredPrompt) {
                    document.getElementById('install-banner').style.display = 'block';
                    document.getElementById('android-msg').style.display = 'block';
                }
            }, 3000);
        }
    }

    // File handling
    const MAXMB = <?php echo (int)$settings['max_file_size_mb']; ?>;
    const MAXPG = <?php echo (int)$settings['max_pages']; ?>;
    let files = [];
    
    document.getElementById('f_file').onchange = function(e) { 
        addFiles(e.target.files); 
        e.target.value = ''; 
    };
    document.getElementById('f_cam').onchange = function(e) { 
        addFiles(e.target.files); 
        e.target.value = ''; 
    };
    document.getElementById('f_gallery').onchange = function(e) { 
        addFiles(e.target.files); 
        e.target.value = ''; 
    };
    
    function addFiles(newFiles) {
        for (let f of newFiles) {
            f.rotation = 0;
            files.push(f);
        }
        render();
    }
    
    function render() {
        const list = document.getElementById('file-list');
        
        if (files.length === 0) {
            list.innerHTML = '<div class="empty-state">Select files or take photos to upload</div>';
            return;
        }
        
        list.innerHTML = '';
        files.forEach(function(f, i) {
            const row = document.createElement('div');
            row.className = 'file-row';
            
            let thumb = '';
            let rotBtns = '';
            const isPdf = (f.type === 'application/pdf' || f.name.match(/\.pdf$/i));
            
            if (f.type.startsWith('image/')) {
                thumb = '<img src="' + URL.createObjectURL(f) + '" class="thumb" style="transform:rotate(' + f.rotation + 'deg)" onclick="preview(' + i + ')" title="Tap to preview">';
                rotBtns = '<button class="action-btn rot-btn" onclick="rotate(' + i + ',-90)" title="Rotate left"></button>' +
                          '<button class="action-btn rot-btn" onclick="rotate(' + i + ',90)" title="Rotate right"></button>';
            } else if (isPdf) {
                thumb = '<div class="thumb pdf-thumb">📄</div>';
                rotBtns = '<button class="action-btn rot-btn" onclick="rotate(' + i + ',-90)" title="Rotate left"></button>' +
                          '<button class="action-btn rot-btn" onclick="rotate(' + i + ',90)" title="Rotate right"></button>';
            }
            
            row.innerHTML = 
                '<div class="file-info">' + thumb + '<span>' + escapeHtml(f.name) + '</span></div>' +
                '<div class="file-actions">' + rotBtns +
                '<button class="action-btn" onclick="move(' + i + ',-1)" ' + (i === 0 ? 'disabled' : '') + ' title="Move up">↑</button>' +
                '<button class="action-btn" onclick="move(' + i + ',1)" ' + (i === files.length - 1 ? 'disabled' : '') + ' title="Move down">↓</button>' +
                '<button class="action-btn del-btn" onclick="remove(' + i + ')" title="Remove">✕</button>' +
                '</div>';
            
            list.appendChild(row);
        });
    }
    
    

    // Image preview modal (mobile-friendly)
    let previewIndex = null;
    window.preview = function(i) {
        const f = files[i];
        if (!f || !f.type || !f.type.startsWith('image/')) return;
        previewIndex = i;
        const modal = document.getElementById('ppuModal');
        const img = document.getElementById('ppuModalImg');
        const title = document.getElementById('ppuModalTitle');
        title.textContent = f.name;
        img.src = URL.createObjectURL(f);
        img.style.transform = 'rotate(' + (f.rotation || 0) + 'deg)';
        modal.style.display = 'block';
    };

    window.closePreview = function() {
        const modal = document.getElementById('ppuModal');
        const img = document.getElementById('ppuModalImg');
        if (img && img.src) { try { URL.revokeObjectURL(img.src); } catch(e){} }
        if (modal) modal.style.display = 'none';
        previewIndex = null;
    };

    window.rotatePreview = function(deg) {
        if (previewIndex === null) return;
        rotate(previewIndex, deg);
        const f = files[previewIndex];
        const img = document.getElementById('ppuModalImg');
        if (img && f) img.style.transform = 'rotate(' + (f.rotation || 0) + 'deg)';
    };
window.rotate = function(i, deg) {
        files[i].rotation = (files[i].rotation + deg + 360) % 360;
        render();
    };
    
    window.move = function(i, dir) {
        const newIndex = i + dir;
        if (newIndex >= 0 && newIndex < files.length) {
            const temp = files[i];
            files[i] = files[newIndex];
            files[newIndex] = temp;
            render();
        }
    };
    
    window.remove = function(i) {
        files.splice(i, 1);
        render();
    };
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    window.upload = async function() {
        if (files.length === 0) {
            alert('Please select at least one file or take a photo.');
            return;
        }
        
        const btn = document.getElementById('upload-btn');
        const msg = document.getElementById('msg');
        
        btn.disabled = true;
        msg.style.display = 'none';
        
        try {
            let blob, filename;
            const isDoc = files.some(f => f.name.match(/\.docx?$/i));
            
            if (isDoc) {
                if (files.length > 1) {
                    throw new Error('Word documents cannot be merged. Please upload only one document, or use PDF/images.');
                }
                blob = files[0];
                filename = 'bulletin.' + blob.name.split('.').pop().toLowerCase();
                btn.innerText = 'Uploading...';
            } else {
                btn.innerText = 'Creating PDF...';
                
                const PDFLib = window.PDFLib;
                const pdf = await PDFLib.PDFDocument.create();
                
                for (let f of files) {
                    const buffer = await f.arrayBuffer();
                    
                    if (f.type === 'application/pdf' || f.name.match(/\.pdf$/i)) {
                        const srcPdf = await PDFLib.PDFDocument.load(buffer);
                        if (pdf.getPages().length + srcPdf.getPageCount() > MAXPG) {
                            throw new Error('Too many pages. Maximum: ' + MAXPG);
                        }
                        const pages = await pdf.copyPages(srcPdf, srcPdf.getPageIndices());
                        pages.forEach(p => { if (f.rotation !== 0) { p.setRotation(PDFLib.degrees(f.rotation)); } pdf.addPage(p); });
                    } else {
                        if (pdf.getPages().length >= MAXPG) {
                            throw new Error('Too many pages. Maximum: ' + MAXPG);
                        }
                        
                        let img;
                        if (f.type === 'image/png' || f.name.match(/\.png$/i)) {
                            img = await pdf.embedPng(buffer);
                        } else {
                            img = await pdf.embedJpg(buffer);
                        }
                        
                        const page = pdf.addPage([595, 842]); // A4
                        const { width, height } = img.scaleToFit(555, 802);
                        page.drawImage(img, {
                            x: (595 - width) / 2,
                            y: (842 - height) / 2,
                            width: width,
                            height: height
                        });
                        
                        if (f.rotation !== 0) {
                            page.setRotation(PDFLib.degrees(f.rotation));
                        }
                    }
                }
                
                blob = new Blob([await pdf.save()], { type: 'application/pdf' });
                filename = 'bulletin.pdf';
            }
            
            // Check file size
            if (blob.size > MAXMB * 1024 * 1024) {
                throw new Error('File too large (' + (blob.size / 1024 / 1024).toFixed(1) + 'MB). Maximum: ' + MAXMB + 'MB');
            }
            
            btn.innerText = 'Uploading...';
            
            const formData = new FormData();
            formData.append('file', blob, filename);
            formData.append('diocese', <?php echo json_encode($dio); ?>);
            formData.append('parish', <?php echo json_encode($par); ?>);
            formData.append('key', <?php echo json_encode($key); ?>);
            
            const response = await fetch(<?php echo json_encode(rest_url('ppu/v1/upload')); ?>, {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (result.status !== 'success') {
                throw new Error(result.message || 'Upload failed. Please try again.');
            }
            
            msg.className = 'msg suc';
            msg.innerHTML = '✅ <strong>Bulletin Published!</strong><br><br>' +
                '<a href="' + escapeHtml(result.file_url) + '" target="_blank" style="color:#155724;font-weight:bold;">View Bulletin →</a>';
            msg.style.display = 'block';
            
            files = [];
            render();
            
        } catch (e) {
            msg.className = 'msg err';
            msg.textContent = '❌ ' + e.message;
            msg.style.display = 'block';
            console.error(e);
        }
        
        btn.disabled = false;
        btn.innerText = '📤 Upload Bulletin';
    };
    
    // Initial render
    render();
})();
</script>

</body>
</html>
<?php
}