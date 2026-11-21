<?php
/**
 * Plugin Name: ParishPress Harvester Bridge
 * Description: Export a public bulletin source for the Parish Harvester from the existing Parish Press Uploader.
 * Version: 1.0.0
 */
defined('ABSPATH') || exit;

add_action('admin_menu', function () {
    add_management_page('ParishPress sources', 'ParishPress sources', 'manage_options', 'parishpress-sources', 'pphb_sources_page');
});

function pphb_sources_page() {
    if (!current_user_can('manage_options')) {
        return;
    }
    echo '<div class="wrap"><h1>ParishPress sources</h1>';
    if (!function_exists('ppu_get_parishes') || !function_exists('ppu_public_parish_slug')) {
        echo '<p>Activate the Parish Press Uploader first.</p></div>';
        return;
    }
    $parishes = ppu_get_parishes();
    echo '<p>Choose the uploader parish and enter its identifiers from the Harvester repository. Check the public bulletin opens before submitting the recipe for review.</p>';
    echo '<form method="post">';
    wp_nonce_field('pphb_recipe');
    echo '<p><label>Uploader parish <select name="ppu_id">';
    foreach ($parishes as $id => $parish) {
        echo '<option value="' . esc_attr($id) . '">' . esc_html($parish['name'] . ' (' . $parish['diocese'] . ')') . '</option>';
    }
    echo '</select></label></p><p><label>Repository diocese folder <input required name="repo_diocese" pattern="[a-z0-9_-]+"></label></p>';
    echo '<p><label>Repository parish key <input required name="repo_key" pattern="[a-z0-9_-]+"></label></p>';
    submit_button('Generate public recipe');
    echo '</form>';
    if (isset($_POST['ppu_id'])) {
        check_admin_referer('pphb_recipe');
        $id = sanitize_key(wp_unslash($_POST['ppu_id']));
        $key = sanitize_key(wp_unslash($_POST['repo_key'] ?? ''));
        $diocese = sanitize_key(wp_unslash($_POST['repo_diocese'] ?? ''));
        if (isset($parishes[$id]) && $key && $diocese && !empty($parishes[$id]['diocese']) && $parishes[$id]['diocese'] !== 'unassigned') {
            $parish = $parishes[$id];
            $url = site_url('bulletin/' . rawurlencode($parish['diocese']) . '/' . rawurlencode(ppu_public_parish_slug($id, $parish)) . '/');
            $recipe = array('version' => 2, 'parish_key' => $key, 'display_name' => $parish['name'], 'diocese' => $diocese,
                'start_url' => $url, 'site_type' => 'permanent_redirect_document', 'playbook_type' => 'direct_download',
                'disable_stale_rescrape_fallback' => true, 'steps' => array(array('action' => 'download', 'url' => $url, 'use_target_url' => true)));
            echo '<p><a href="' . esc_url($url) . '">Check public bulletin</a></p><p>Review for <code>' . esc_html("parishes/recipes/$diocese/$key.json") . '</code></p>';
            echo '<textarea readonly rows="18" class="large-text code">' . esc_textarea(wp_json_encode($recipe, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)) . '</textarea>';
        } else {
            echo '<p>Choose an assigned uploader parish and supply both repository identifiers.</p>';
        }
    }
    echo '</div>';
}
