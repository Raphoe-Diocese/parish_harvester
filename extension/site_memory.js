/**
 * Institutional memory for unusual parish bulletin sites.
 * Saved into recipe JSON on Push and into parishes/site_patterns.json on GitHub.
 */
(() => {
  const CATALOG = {
    oneweb_docx: {
      playbook_type: "oneweb_docx",
      site_type: "oneweb_newsletter",
      page_type: "oneweb_docx",
      recipe_flow: "direct_docx",
      label: "One.com + slow Google preview iframes",
      auto_direct: true,
      skip_goto_on_push: true,
      max_bulletin_pages: 8,
      operator_notes: [
        "Many docs.google.com/viewer iframes load slowly (2–4 min) — ignore previews.",
        "Bulletin is a Word file at onewebmedia/NEWSLETTER D-M-YY.docx — download directly.",
        "Iframe src URLs are in the HTML immediately; no need to wait for previews.",
        "Harvester rewrites the date each Sunday and tries filename variants (spaces before .docx).",
        "28/10/2026 Claudy: NEWSLETTER 25-10-26.docx is 5 pages. Set max_bulletin_pages 8 (default 4 rejects real Word weeklies).",
        "29/10/2026 Carrickmacross PDF also hit Too many pages: 5 — same fix max_bulletin_pages 8 on the recipe.",
      ],
      do_not: [
        "Do not pick the first iframe PDF — often a GDPR or Privacy notice.",
        "Do not use goto-only recipes on this page.",
        "Do not train on financial-statement or admin docx files.",
        "Do not keep the default 4-page cap for a multi-page Word or PDF newsletter.",
      ],
    },
    permanent_redirect_document: {
      playbook_type: "direct_download",
      site_type: "permanent_redirect_document",
      page_type: "permanent_redirect_document",
      recipe_flow: "direct_download",
      label: "Permanent /current-newsletter/ (or same weekly PDF path)",
      auto_direct: true,
      skip_goto_on_push: true,
      disable_stale_rescrape_fallback: true,
      operator_notes: [
        "Same URL every week. It redirects to this Sunday's PDF (Naas / Kildare / Meath / Bellaghy).",
        "Point the recipe at /current-newsletter/ only. Do not pin the dated upload name.",
        "28/10/2026 Bellaghy: when the redirect is last week, leave it stale. Homepage rescrape pulled a pope-francis jpeg.",
        "29/10/2026 Bellaghy: /current-newsletter/ now resolves to 25-Oct-2026.pdf — reharvest; keep disable_stale_rescrape_fallback.",
        "29/10/2026 Blanchardstown: same pattern at blanchardstownparish.ie/current-newsletter/ (archive is /newsletters/ plural).",
        "Always set disable_stale_rescrape_fallback so the referee does not scrape the homepage.",
      ],
      do_not: [
        "Do not pin a dated wp-content filename.",
        "Do not rescrape the homepage when /current-newsletter/ is stale.",
        "Do not download pope-francis, Irish-Bishops, Gaza appeal, or GDPR PDFs from the homepage.",
      ],
    },
    cloud_folder: {
      playbook_type: "cloud_folder",
      site_type: "cloud_folder",
      page_type: "cloud_folder",
      recipe_flow: "click_then_pdf",
      label: "Google Drive / OneDrive dated folder",
      operator_notes: [
        "Pin the parent Parish Newsletters folder only — year folder Drive ids change every January (2026 → 2027 → 2028).",
        "Open parent → click the folder named this year → pick YY.MM.DD.pdf (26.10.25.pdf = 25/10/2026, not 26 October).",
        "Bruckless parent 1jPOi4GRU22vAxeKNe5Y_doBJ3riPh7ZK. Do not pin year folder 1z9goh6… (2026) or 1RjeEY_AYy… (2025).",
        "Harvester replays the year click + dated row each week.",
      ],
      do_not: [
        "Do not pin a year-folder id — it dies next January.",
        "Do not pin a /file/d/ id — it dies when they upload next week.",
        "Do not read YY.MM.DD as DD.MM.YY.",
      ],
    },
    canva_site: {
      playbook_type: "canva_site",
      site_type: "canva_site_bulletin_image",
      page_type: "canva_bulletin_image",
      recipe_flow: "image_stack",
      label: "Canva parish site — photo of printed bulletin",
      operator_notes: [
        "29/10/2026 Ardboe: canva.site hosts the weekly sheet as a photo (no PDF). ardboeparish.com redirects there.",
        "Take durable img[src*=\"_assets/media\"] — skip blob: currentSrc (not re-fetchable).",
        "Media path hash changes when they swap the photo — never pin it.",
        "Other large photos sit beside the sheet — image_stack prefer=largest so next week still wins.",
        "Accessibility tree may miss the image — look at the page / media assets.",
      ],
      do_not: [
        "Do not pin /_assets/media/<hash>.png.",
        "Do not pin blob: URLs.",
        "Do not leave link_only/skip when the bulletin photo is on the Canva page.",
        "Do not Save page as PDF of the whole Canva chrome.",
      ],
    },
    parish_messenger: {
      playbook_type: "parish_messenger",
      site_type: "parish_messenger",
      page_type: "parish_messenger_embed",
      recipe_flow: "click_then_pdf",
      label: "Parish Messenger widget",
      operator_notes: [
        "Wait for widget to load, then click CLICK HERE to load Current Newsletter.",
        "Then capture the PDF download (use_captured_url). Same as Buncrana / Carndonagh.",
        "29/10/2026 Melmount parishnews.html: Messenger click gone — page IS this week's HTML. Use html_text_bulletin print_to_pdf + skip_listing_nav. Sion Mills aliases Melmount (shared collections).",
        "29/10/2026 Sion: a[href$=.pdf] fallback grabbed dead /pdf/090820.pdf (404). Text selectors only when widget is present.",
        "Ignore Gift Aid and Data Entry PDFs in the menu.",
      ],
      do_not: [
        "Do not pick admin PDFs from the widget list.",
        "Do not force Messenger click when parishnews already shows this week's HTML body.",
        "Do not fall back to a[href$=.pdf] on the listing — dead homepage PDFs win the click.",
        "Do not click CatholicIreland Daily Readings links.",
        "Do not harvest Melmount and Sion twice — same bulletin.",
      ],
    },
    weekly_bulletin_download: {
      playbook_type: "weekly_bulletin_download",
      site_type: "sequential_bulletin_number",
      page_type: "weekly_bulletin_download",
      recipe_flow: "direct_download",
      label: "Weekly bulletin list with auto-download",
      auto_direct: true,
      skip_goto_on_push: true,
      operator_notes: [
        "Homepage shows dated rows — click the cloud download on this Sunday's bulletin.",
        "PDF downloads automatically; trainer records the download URL.",
        "Harvester advances /Weekly-Bulletins/NNN/ by weeks since the example date.",
        "Joomla Dropfiles widget: cloud icon is a.mod_downloadlink — clicking the icon inside still counts.",
      ],
      do_not: [
        "Do not use Pick bulletin image — this is a PDF download site.",
        "Do not stop at click-only — need a download capture step.",
      ],
    },
    wix_html: {
      playbook_type: "wix_html",
      site_type: "html_text_bulletin",
      page_type: "wix_html",
      recipe_flow: "html_capture",
      label: "HTML text bulletin (WordPress, Wix, or similar)",
      operator_notes: [
        "Bulletin text is on the web page — not a downloadable PDF file.",
        "Use Save page as PDF on the newsletter article page.",
        "29/10/2026 Clonleigh: start on the homepage, not /category/newsletter/ (that listing lagged a week). Click top Strabane Pastoral Area Newsletter, then print_to_pdf. Publish day can be Sunday, not only Saturday.",
        "29/10/2026 Ballybrack-Killiney: start on news.html, click top Newsletter title (24th & 25th October), print_to_pdf. Do not pin last week's article URL.",
        "29/10/2026 Achonry-Mullinabreena: NEWS.aspx ASP.NET list → click top Parish Newsletter (ArticleDetail) → print_to_pdf. Do not pin articleid. Do not scrape achonrydiocese.org parish card (admin/wrong file).",
      ],
      do_not: [
        "Do not use Pick bulletin image when the page is mostly text paragraphs.",
        "Do not stop at click-only — need print_to_pdf as the final step.",
        "Do not train only on /category/newsletter/ when the homepage already shows a newer post.",
        "Do not pin a dated /news/newsletter-… URL.",
        "Do not pin ArticleDetail.aspx?articleid=… on ASP.NET parish news lists.",
      ],
    },
    dated_pdf_bulletin: {
      playbook_type: "dated_pdf_bulletin",
      site_type: "dated_pdf_path",
      page_type: "direct_pdf",
      recipe_flow: "direct_download",
      label: "Word → PDF bulletin at /pdf/DDMMYY.pdf",
      operator_notes: [
        "Bulletin is a real PDF (often made in Microsoft Word → Print to PDF).",
        "Tab title may say .docx or .jpg — ignore that; check the address bar ends in .pdf.",
        "On the PDF page: tap Save this PDF — saves the full https://… address for Sunday harvest.",
        "Or start on parishnews.html → point at this week's link → Yes → Save this PDF.",
        "Harvester rewrites DDMMYY in the URL each Sunday (e.g. 140626 → 210626).",
      ],
      do_not: [
        "Do not use use_page_url only — GitHub cannot read Chrome's internal PDF viewer address.",
        "Do not worry if Document Properties title mentions Microsoft Word.",
        "Do not skip a news.html page because view-source is empty — the /pdf/DDMMYY.pdf links are often JavaScript.",
      ],
    },
    js_dated_pdf_list: {
      playbook_type: "dated_pdf_bulletin",
      site_type: "predicted_dated_pdf",
      page_type: "direct_pdf",
      recipe_flow: "direct_download",
      label: "JS-rendered /pdf/DDMMYY.pdf list",
      operator_notes: [
        "Listing HTML scrape looks empty. Live DOM has Sunday, Dth Month YYYY → /pdf/DDMMYY.pdf.",
        "Save this PDF. Harvester rewrites DDMMYY each Sunday (predicted_dated_pdf).",
        "Prefer HTTP if HTTPS TLS fails (Tempo / Pobal).",
      ],
      do_not: [
        "Do not skip because news.html looks empty.",
        "Do not pin one week's filename.",
      ],
    },
    js_overwritten_html_newsletter: {
      playbook_type: "html_text_bulletin",
      site_type: "html_text_bulletin",
      page_type: "html_text_bulletin",
      recipe_flow: "html_capture",
      label: "JS-injected HTML newsletter (overwritten weekly)",
      operator_notes: [
        "parishnews.htm view-source is blank. After JS, this week's newsletter is on the page.",
        "Save page as PDF with skip_listing_nav. Wait for the embed to load.",
        "29/10/2026 Ardstraw East: Latest Parish Newsletter on parishnews.html already has this week's body; Past Newsletters list can lag. Print the page — do not click Past newest when Latest is filled.",
        "109.228.27.39/templates/?a= is a print view — do not pin that article id.",
      ],
      do_not: [
        "Do not skip because HTTP scrape is blank.",
        "Do not use the 109.228 IP as the start URL.",
        "Do not harvest DataEntry / GDPR forms from the Past list.",
      ],
    },
    mdocs_download_list: {
      playbook_type: "mdocs_download_list",
      site_type: "mdocs_bulletin_list",
      page_type: "mdocs_bulletin_list",
      recipe_flow: "click_then_pdf",
      label: "mDocs PDF bulletin table",
      operator_notes: [
        "mDocs WordPress plugin lists dated PDFs — newest row is usually at the top.",
        "Click Download on this week's row, then capture PDF download (not Save page as PDF).",
        "Slow sites: use http:// if HTTPS certificate is expired (portstewartparish.website).",
        "Harvester waits up to 7 minutes for the table on very slow hosts.",
      ],
      do_not: [
        "Do not use Save page as PDF — bulletins are real PDF files in the mDocs table.",
        "Do not use https://portstewartparish.website — certificate expired; use http://.",
      ],
    },
    wp_block_file_bulletin: {
      playbook_type: "permanent_bulletin_page",
      site_type: "wp_block_file_bulletin",
      page_type: "wp_block_file_bulletin",
      recipe_flow: "direct_download",
      label: "WordPress permanent bulletin page (wp-block-file)",
      operator_notes: [
        "Permanent /parish-bulletin/ URL — PDF filename changes weekly under /wp-content/uploads/YYYY/MM/.",
        "On the bulletin page: tap the green Save bulletin PDF (from embed) button.",
        "Use url_pattern *bulletin*.pdf — never pin a dated filename.",
      ],
      do_not: [
        "Do not train on the homepage — use the dedicated bulletin page only.",
        "Do not pin saintanthony.co.uk if the parish moved to saintanthonys.uk.",
      ],
    },
    google_drive_static: {
      playbook_type: "direct_download",
      site_type: "google_drive_static",
      page_type: "google_drive_static",
      recipe_flow: "direct_download",
      label: "Google Drive permanent bulletin file",
      auto_direct: true,
      skip_goto_on_push: true,
      operator_notes: [
        "Permanent Google Drive file — parish replaces the PDF in the same link each week.",
        "Train on drive.google.com/file/d/…/view (preview page), not the instant-download URL.",
        "Harvester downloads via drive.usercontent.google.com/download?id=… automatically.",
      ],
      do_not: [
        "Do not open the usercontent download link to train — the tab closes instantly.",
        "Do not add a goto step to the download URL.",
      ],
    },
    joomla_dropfiles: {
      playbook_type: "weekly_bulletin_download",
      site_type: "joomla_dropfiles",
      page_type: "weekly_bulletin_download",
      recipe_flow: "click_then_download",
      label: "Joomla Dropfiles cloud download (.docx → PDF)",
      operator_notes: [
        "Joomla Dropfiles — cloud ↓ icon (a.mod_downloadlink) serves Word .docx.",
        "Or homepage /Newsletters/NNN/ rows — newest is usually at the top (Banagher 25 Oct id 406).",
        "Click newest_dated at the top. Do not pin a June id at the bottom.",
        "If the pretty /files/… URL is hotlink-blocked, replay retries task=frontfile.download.",
        "Do not record diocese GDPR/Privacy PDFs — only mod_downloadlink on the parish host.",
      ],
      do_not: [
        "Do not save a download URL from downandconnor.org or other diocese admin PDFs.",
        "Do not use Pick bulletin image — this is a file download site.",
        "Do not set bulletin_position bottom when newest Newsletter is at the top.",
      ],
    },
    stacked_image_bulletin: {
      playbook_type: "stacked_image_bulletin",
      site_type: "stacked_image_bulletin",
      page_type: "stacked_image_bulletin",
      recipe_flow: "image_stack",
      label: "Stacked JPEG bulletin images (top N each week)",
      operator_notes: [
        "Bulletins are full-page images stacked on one page — newest week at the top.",
        "Pick the first two images, or use Pick another image too after the first.",
        "Harvester grabs the top N large images automatically each Sunday — no dated URLs.",
      ],
      do_not: [
        "Do not hardcode one image URL — it goes stale every week.",
        "Do not Save page as PDF — that captures every old bulletin on the page.",
      ],
    },
    onewebmedia_pdf_list: {
      playbook_type: "pdf_download_list",
      site_type: "pdf_link_list",
      page_type: "pdf_link_list",
      recipe_flow: "click_then_pdf",
      label: "One.com weekly PDF list (onewebmedia)",
      operator_notes: [
        "onewebmedia/*.pdf — newest row is usually a DDMMYYYY name or hashed S25C with dated link text.",
        "If the HTTPS certificate is expired, harvest must ignore TLS errors (Playwright).",
        "Do not pin a dated or hashed filename.",
      ],
      do_not: [
        "Do not pin a dated or hashed onewebmedia filename.",
        "Do not use plain HTTP scrape when the certificate is expired.",
      ],
    },
    wix_ugd_dated_pdf: {
      playbook_type: "wix_html",
      site_type: "html_text_bulletin",
      page_type: "pdf_link_list",
      recipe_flow: "click_then_pdf",
      label: "Wix hashed PDF with dated link text",
      operator_notes: [
        "Wix /_files/ugd/ hashes have no date — the date is in the link text.",
        "Click newest_dated, then download. Never pin the hash.",
      ],
      do_not: [
        "Do not pin a hashed /_files/ugd/ URL.",
        "Do not use http_scrape_newest_pdf on hashed Wix files.",
        "Do not download rota or vocations PDFs.",
      ],
    },
    office_rtf_newsletter: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Weekly RTF newsletter",
      operator_notes: [
        "Weekly file is .rtf (Word). Harvester converts it with LibreOffice.",
        "Pick the newest dated .rtf — do not invent a PDF name.",
      ],
      do_not: ["Do not pin a dated .rtf.", "Do not invent a PDF filename."],
    },
    mcn_live_parish_page: {
      playbook_type: "mcn_pdf_near_camera",
      site_type: "mcn_live_parish_page",
      page_type: "mcn_live_parish_page",
      recipe_flow: "direct_download",
      label: "MCN camera page newsletter (not the webcam)",
      operator_notes: [
        "Frank 29/10/2026: MCN is a prime dig for unknown bulletins — search mcn.live Cameras by county, then open the parish Camera page.",
        "Frank trained this: the weekly PDF sits on the mcn.live /Camera/ page (not the video stream).",
        "Harvest reads the church profile JSON, then downloads the newsletter URL. Recipe already knows where on the page.",
        "Start at the camera URL. Do not pin a dated PDF or CloudFront UUID.",
      ],
      do_not: [
        "Do not harvest the webcam video.",
        "Do not pin a dated newsletter filename.",
        "Do not skip MCN when the diocese card has no website.",
      ],
    },
    churchmedia_newsletter: {
      playbook_type: "churchmedia_latest_newsletter",
      site_type: "churchmedia_newsletter",
      page_type: "churchmedia_newsletter",
      recipe_flow: "direct_download",
      label: "churchmedia.tv View Our Latest Newsletter",
      operator_notes: [
        "Livestream page. Bulletin is the Latest Newsletter button.",
        "Harvest uses getChannelAbout. Portaferry proved this.",
      ],
      do_not: [
        "Do not pin /newsletter/<token>.….pdf — the token dies next week.",
      ],
    },
    joomla_images_newsletter: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Joomla /images/newsletter/YY-MM-DD.pdf",
      operator_notes: [
        "theparishioner.ie and onefaith.ie list /images/newsletter/YY-MM-DD.pdf.",
        "31/10/2026 theparishioner proved 26-10-25.pdf and 26-11-01.pdf. Scrape the listing.",
        "The HTML article link is not the PDF.",
        "31/10/2026 onefaith newest proved file was 26-10-12.pdf. That is behind the 25/10 target.",
      ],
      do_not: [
        "Do not pin YY-MM-DD.pdf.",
        "Do not print the HTML article as the bulletin.",
        "Do not call onefaith fresh while its newest PDF is 12/10/2026.",
      ],
    },
    ddmmyyyy_listing_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Listing PDF named DDMMYYYY.pdf",
      operator_notes: [
        "31/10/2026 Birr /newsletter/ linked 01112026.pdf and 25102026.pdf. Both application/pdf.",
      ],
      do_not: ["Do not pin the DDMMYYYY.pdf name."],
    },
    spelled_month_listing_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Listing PDF named Month-Dth-YYYY",
      operator_notes: [
        "31/10/2026 Bodyke /newsletter/ linked November-1st-2026 and October-25th-2026 PDFs.",
        "/parish-newsletter/ was a 404. Use /newsletter/.",
      ],
      do_not: ["Do not pin the dated filename."],
    },
    kerry_card_yyyymmdd_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Kerry diocese card PDF named YYYY-MM-DD.pdf",
      operator_notes: [
        "31/10/2026 Baile an Fheirtearaigh card proved 2026-11-01.pdf (application/pdf, 01/11/2026).",
      ],
      do_not: [
        "Do not pin the dated PDF.",
        "Do not use the diocese Facebook page as the parish link.",
      ],
    },
    wp_json_weekend_range_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "wp_json_newest_media",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Bree weekend PDF in the media library",
      operator_notes: [
        "31/10/2026 media library has 3744-Oct-31st-Nov-1st.pdf. Proved application/pdf. Media date 30/10/2026.",
      ],
      do_not: ["Do not pin 3744-Oct-31st-Nov-1st.pdf."],
    },
    booterstown_sunday_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "wp_json_newest_media",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Booterstown Sun-D-Month-YYYY PDF in wp-json",
      operator_notes: [
        "31/10/2026 wp-json proved Sun-1-November-2026 and Sun-25-October-2026 PDFs. Harvest 41244478540 asked for Sun-25-October and the browser said miss, then timed out. Do not send it again.",
      ],
      do_not: ["Do not pin the dated filename.", "Do not harvest the front.png as the bulletin."],
    },
    homepage_pdf_when_wpjson_404: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Homepage PDF when wp-json media is 404",
      operator_notes: [
        "31/10/2026 Borrisokane /wp-json/wp/v2/media returned HTTP 404. The homepage links the PDF. Scrape that page.",
      ],
      do_not: ["Do not pin the dated filename.", "Do not keep calling wp-json when it returns 404."],
    },
    link_text_undated_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Undated PDF, date in the link text",
      operator_notes: [
        "31/10/2026 Doora-Barefield doora-Barefield.pdf has no date in the name. The link says 1st November.",
      ],
      do_not: ["Do not pin doora-Barefield.pdf.", "Do not take 18th-Oct.pdf while the 1 November link is listed."],
    },
    category_week_jpg: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_images",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Newsletter JPG on the category page",
      operator_notes: [
        "31/10/2026 Durrow category has newsletter-25-oct-2026.jpg. Skip the resized copy.",
      ],
      do_not: ["Do not pin the dated filename.", "Do not take the 300px resized copy."],
    },
    yy_mm_d_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "YY-MM-D.pdf with the day unpadded",
      operator_notes: [
        "31/10/2026 Kilbrittain 26-11-1.pdf is 01/11/2026. The link text does not carry the date.",
      ],
      do_not: ["Do not pin 26-11-1.pdf.", "Do not read 26-11-1 as 26 November."],
    },
    prefix_ddmmyy_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Parishes Together prefix-DD-MM-YY.pdf",
      operator_notes: [
        "31/10/2026 proved Carraig, Glanmire, Glounthaune, and Wgh files named Prefix-25-10-26.pdf. Each prefix is one parish.",
      ],
      do_not: [
        "Do not pin the dated filename.",
        "Do not scrape another parish prefix into this recipe.",
      ],
    },
    bantry_family_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Bantry family weekly PDF, harvest once",
      operator_notes: [
        "One PDF covers Bantry, Caheragh, Goleen, Muintir Bhaire, and Schull. Harvest once under bantry.",
      ],
      do_not: [
        "Do not pin the dated filename.",
        "Do not add recipes for caheragh, goleen, muintirbhaire, or schull.",
      ],
    },
    iso_newsletter_pdf: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "newsletter-YYYY-MM-DD.pdf",
      operator_notes: [
        "31/10/2026 Churchtown proved newsletter-2026-11-01.pdf. Date is in the filename.",
      ],
      do_not: ["Do not pin the dated filename."],
    },
    mayo_ie_newsletters: {
      playbook_type: "pdf_download_list",
      site_type: "http_scrape_newest_pdf",
      page_type: "pdf_link_list",
      recipe_flow: "direct_download",
      label: "Mayo County Council parish-newsletters",
      operator_notes: [
        "Hub: https://www.mayo.ie/parish-newsletter shows many Mayo parishes with DD-MM-YYYY on each card (Frank 29/10/2026 — lots already 25-10-2026).",
        "mayo.ie hosts parish PDFs (Belmullet proved 04/10/2026). Also covers Killala/Tuam/Achonry leftovers when the parish or diocese site is dead.",
        "Date is in the link text and filename. Scrape the parish listing under /en-ie/parish-newsletters/…",
      ],
      do_not: [
        "Do not pin the getmedia GUID.",
        "Do not treat a PNG as a PDF recipe.",
        "Do not skip mayo.ie when the official diocese card has no file.",
      ],
    },
    google_search_parish_host: {
      playbook_type: "link_only",
      site_type: "link_only",
      page_type: "kitchen_sink_search",
      recipe_flow: "html_capture",
      label: "Search AIs + dig for parish site / Drive / MCN",
      operator_notes: [
        "Frank 29/10/2026: use every search AI / website-finder available (Cursor WebSearch/Google and any other search agent in the chat) — not memory.",
        "Also dig mcn.live and churchmedia.tv. Read old bulletin text for printed website, Google Drive, OneDrive, Outlook/SharePoint, Dropbox links.",
        "Query: \"{parish} parish newsletter\", \"bulletin\", \"facebook\", \"mcn.live\", \"churchmedia\", \"google drive newsletter\".",
        "Open every promising href. Facebook stays clickable only — do not scrape posts.",
      ],
      do_not: [
        "Do not invent a URL from memory when search can find the live host.",
        "Do not scrape Facebook or Instagram posts.",
        "Do not take Church of Ireland twins.",
        "Do not skip MCN/churchmedia when the official card is empty.",
      ],
    },
    churchservices_tv_pointer: {
      playbook_type: "link_only",
      site_type: "link_only",
      page_type: "webcam_pointer",
      recipe_flow: "html_capture",
      label: "churchservices.tv webcam — pointer only",
      operator_notes: [
        "Webcam first. Look on the same page for a real newsletter file.",
        "Else keep the parish website. Do not invent a PDF.",
      ],
      do_not: [
        "Do not harvest the livestream as a bulletin.",
        "Do not invent a PDF because a webcam exists.",
      ],
    },
    faithful_ie_family_newsletters: {
      playbook_type: "pdf_download_list",
      site_type: "pdf_link_list",
      page_type: "pdf_link_list",
      recipe_flow: "click_then_pdf",
      label: "faithful.ie family newsletter list (Cork)",
      operator_notes: [
        "Cork family listing (OneFaith, West Cork, The Parishioner, OurParish, Bantry, Cathedral, Parishes Together, Kilbrittain).",
        "Point at this week's PDF on this page. Harvest the list once.",
        "Official /parishes/Name may 404 — stay on /newsletter, /newsletters or /notices.",
      ],
      do_not: [
        "Do not pin a dated PDF filename.",
        "Do not make a second recipe for each parish name on the same list.",
        "Do not treat familyofparishes.ie/news as a weekly newsletter — notices only.",
      ],
    },
    pdf_download_list: {
      playbook_type: "pdf_download_list",
      site_type: "pdf_link_list",
      page_type: "pdf_link_list",
      recipe_flow: "click_then_pdf",
      label: "PDF download list (newest dated row each week)",
      operator_notes: [
        "This page lists bulletin PDFs — the newest is usually at the top, but some parishes put it at the bottom.",
        "Point at this week's bulletin link (Download File / Parish News). Harvester picks the newest dated PDF each Sunday.",
        "29/10/2026 Baldoyle/Ballinteer: pinned 18 Oct downloads went stale while 25 Oct files were already listed — prefer http_scrape_newest_pdf; never pin the download URL.",
        "01/11/2026 Sunday harvest: if this Sunday's PDF is not listed yet, keep last Sunday's file. Rerun 41313748997 kept 43 of those 25/10/2026 files. From Monday that file is stale.",
      ],
      do_not: [
        "Do not pin a dated filename in the selector or download step (e.g. Newsletter-18th-October.pdf) — it breaks next week.",
        "Do not pick GDPR, Gift Aid, or financial statement PDFs.",
      ],
    },
  };

  const _DDMMYY_PDF_RE = /\/pdf\/\d{6}\.pdf/i;

  const _recipeUsesDatedPdfPath = (recipe = {}) => {
    const urls = [
      String(recipe.start_url || ""),
      ...(Array.isArray(recipe.steps) ? recipe.steps : []).map((s) =>
        String(s?.url || s?.href || "")
      ),
    ];
    return urls.some((u) => _DDMMYY_PDF_RE.test(u));
  };

  const _recipeUsesImageStack = (recipe = {}) =>
    (Array.isArray(recipe.steps) ? recipe.steps : []).some(
      (step) => String(step?.action || "").trim() === "image_stack"
    );

  const _recipeLooksLikeMdocs = (recipe) => {
    if (!recipe || typeof recipe !== "object") return false;
    if (String(recipe.site_type || "").includes("mdocs")) return true;
    if (String(recipe.playbook_type || "").includes("mdocs")) return true;
    return (Array.isArray(recipe.steps) ? recipe.steps : []).some((step) => {
      const blob = `${step?.href || ""} ${step?.url || ""} ${step?.selector || ""}`;
      return /mdocs-file|table\.mdocs|mdocs-download/i.test(blob);
    });
  };

  const _recipeLooksLikeDropfiles = (recipe) => {
    if (!recipe || typeof recipe !== "object") return false;
    if (String(recipe.site_type || "").includes("dropfiles")) return true;
    return (Array.isArray(recipe.steps) ? recipe.steps : []).some((step) =>
      /mod_downloadlink/i.test(String(step?.selector || ""))
    );
  };

  const getForPageType = (pageType, recipe = null, pageCtx = null) => {
    const safeRecipe = recipe && typeof recipe === "object" ? recipe : {};
    const key = String(pageType || "").trim();
    const fpId = String(pageCtx?.htmlFingerprint || "").trim();
    if (fpId === "mdocs_bulletin_table" || _recipeLooksLikeMdocs(safeRecipe)) {
      return CATALOG.mdocs_download_list;
    }
    if (fpId === "google_drive_file" || key === "google_drive_static") {
      return CATALOG.google_drive_static;
    }
    if (fpId === "wp_block_file_bulletin" || key === "wp_block_file_bulletin") {
      return CATALOG.wp_block_file_bulletin;
    }
    if (fpId === "joomla_dropfiles_weekly" || _recipeLooksLikeDropfiles(safeRecipe)) {
      return CATALOG.joomla_dropfiles;
    }
    if (fpId === "stacked_image_bulletin" || _recipeUsesImageStack(safeRecipe)) {
      return CATALOG.stacked_image_bulletin;
    }
    if (fpId === "onewebmedia_pdf_list") {
      return CATALOG.onewebmedia_pdf_list;
    }
    if (fpId === "wix_ugd_dated_pdf") {
      return CATALOG.wix_ugd_dated_pdf;
    }
    if (fpId === "office_rtf_newsletter") {
      return CATALOG.office_rtf_newsletter;
    }
    if (fpId === "js_dated_pdf_list") {
      return CATALOG.js_dated_pdf_list;
    }
    if (fpId === "js_overwritten_html_newsletter") {
      return CATALOG.js_overwritten_html_newsletter;
    }
    if (fpId === "faithful_ie_family_newsletters") {
      return CATALOG.faithful_ie_family_newsletters;
    }
    const start = String(safeRecipe.start_url || pageCtx?.url || "").toLowerCase();
    if (
      start.includes("/current-newsletter") ||
      key === "permanent_redirect_document" ||
      key === "current-newsletter" ||
      String(safeRecipe.site_type || "").includes("permanent_redirect")
    ) {
      return CATALOG.permanent_redirect_document;
    }
    if (start.includes("mcn.live")) {
      return CATALOG.mcn_live_parish_page;
    }
    if (start.includes("churchmedia.tv")) {
      return CATALOG.churchmedia_newsletter;
    }
    if (start.includes("mayo.ie")) {
      return CATALOG.mayo_ie_newsletters;
    }
    if (
      start.includes("theparishioner.ie") ||
      start.includes("onefaith.ie") ||
      start.includes("/images/newsletter/")
    ) {
      return CATALOG.joomla_images_newsletter;
    }
    if (start.includes("stbrendansbirr.ie")) {
      return CATALOG.ddmmyyyy_listing_pdf;
    }
    if (start.includes("bodyketuamgraneyparish.ie")) {
      return CATALOG.spelled_month_listing_pdf;
    }
    if (start.includes("dioceseofkerry.ie")) {
      return CATALOG.kerry_card_yyyymmdd_pdf;
    }
    if (start.includes("bree.ie")) {
      return CATALOG.wp_json_weekend_range_pdf;
    }
    if (start.includes("booterstownparish.ie")) {
      return CATALOG.booterstown_sunday_pdf;
    }
    if (start.includes("borrisokaneparish.ie")) {
      return CATALOG.homepage_pdf_when_wpjson_404;
    }
    if (start.includes("parishestogether.ie")) {
      return CATALOG.prefix_ddmmyy_pdf;
    }
    if (start.includes("bantryfamilyofparishes.ie")) {
      return CATALOG.bantry_family_pdf;
    }
    if (start.includes("churchtownparish.com")) {
      return CATALOG.iso_newsletter_pdf;
    }
    if (start.includes("castleconnellparish.ie") || start.includes("clarecastleballyeaparish.ie") || start.includes("imeallboirne.ie") || start.includes("ennisparish.com") || start.includes("inaghkilnamonaparish.ie")) {
      return CATALOG.spelled_month_listing_pdf;
    }
    if (start.includes("doorabarefieldparish.ie")) {
      return CATALOG.link_text_undated_pdf;
    }
    if (start.includes("durrow.ie")) {
      return CATALOG.category_week_jpg;
    }
    if (start.includes("kilbrittainparish.ie")) {
      return CATALOG.yy_mm_d_pdf;
    }
    if (start.includes("churchservices.tv")) {
      return CATALOG.churchservices_tv_pointer;
    }
    if (_recipeUsesDatedPdfPath(safeRecipe)) {
      return CATALOG.dated_pdf_bulletin;
    }
    if (key === "pdf_link_list" || key === "pdf_links") {
      return CATALOG.pdf_download_list;
    }
    return CATALOG[key] || null;
  };

  const enrichRecipe = (recipe, pageCtx = {}) => {
    const base = recipe && typeof recipe === "object" ? { ...recipe } : {};
    const memory = getForPageType(pageCtx.type, base, pageCtx);
    if (!memory) return base;

    base.playbook_type = memory.playbook_type;
    base.site_type = memory.site_type;
    if (memory.auto_direct) base.auto_direct = true;
    if (memory.disable_stale_rescrape_fallback) {
      base.disable_stale_rescrape_fallback = true;
    }
    if (memory.ignore_https_errors) {
      base.ignore_https_errors = true;
    }
    if (memory.max_bulletin_pages && !base.max_bulletin_pages) {
      base.max_bulletin_pages = memory.max_bulletin_pages;
    }
    base.operator_notes = [...memory.operator_notes];
    base.do_not = [...memory.do_not];

    if (memory.skip_goto_on_push && Array.isArray(base.steps)) {
      const hasDownload = base.steps.some((s) => String(s?.action || "").toLowerCase() === "download");
      if (hasDownload) {
        base.steps = base.steps.filter((s) => String(s?.action || "").toLowerCase() !== "goto");
      }
    }

    return base;
  };

  const patternPayloadFromPage = (pageCtx = {}, recipe = {}) => {
    const memory = getForPageType(pageCtx.type, recipe, pageCtx);
    const lib = globalThis.PhPatternLibrary;
    if (!lib) return null;
    const page = lib.fingerprintFromPage(pageCtx);
    const rec = lib.fingerprintFromRecipe(recipe);
    if (memory) {
      page.page_type = memory.page_type;
      rec.recipe_flow = memory.recipe_flow;
    }
    return {
      page,
      recipe: rec,
      operator_notes: memory?.operator_notes || recipe.operator_notes || [],
      do_not: memory?.do_not || recipe.do_not || [],
      label: memory?.label || "",
      html: globalThis.PhHtmlFingerprint?.toPatternPayload?.(pageCtx.fingerprintScan) || undefined,
    };
  };

  const formatHintBlock = (memoryOrNotes) => {
    if (!memoryOrNotes) return "";
    const notes = Array.isArray(memoryOrNotes)
      ? memoryOrNotes
      : memoryOrNotes.operator_notes || [];
    const donts = memoryOrNotes.do_not || [];
    const lines = [];
    if (notes.length) {
      lines.push("Remember:");
      notes.forEach((n) => lines.push(`• ${n}`));
    }
    if (donts.length) {
      lines.push("Avoid:");
      donts.forEach((n) => lines.push(`• ${n}`));
    }
    return lines.join("\n");
  };

  window.ph_site_memory = {
    CATALOG,
    getForPageType,
    enrichRecipe,
    patternPayloadFromPage,
    formatHintBlock,
  };
})();
