"""Indonesian (id) translations for the crawl4md Streamlit app."""

from __future__ import annotations

from app_support.i18n._types import Strings

STRINGS_ID: Strings = {
    # ── Page ──────────────────────────────────────────────────────────────
    "PAGE_TITLE": ":material/travel_explore: Langkah 1 - Jelajahi Situs Web",
    "PAGE_SUBTITLE": (
        "Arahkan ke situs web mana pun dan crawl4md akan mengikuti tautan, "
        "mengekstrak konten utama dari setiap halaman, dan menyimpan semuanya "
        "sebagai file Markdown yang bersih dan mudah dibaca."
    ),
    "SESSION_PREFIX": "Sesi: {session_id}",
    "SESSION_LOADING": "Memuat sesi browser...",
    "SESSION_SELECTOR_LABEL": "ID Sesi",
    "SESSION_EXPIRY_CAPTION": "Sesi ini akan kedaluwarsa dalam {days} hari \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_SINGULAR": "Sesi ini akan kedaluwarsa dalam 1 hari \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_DAYS_HOURS": "Sesi ini akan kedaluwarsa dalam {days} hari dan {hours} jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_DAY_HOURS": "Sesi ini akan kedaluwarsa dalam 1 hari dan {hours} jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_DAYS_HOUR": "Sesi ini akan kedaluwarsa dalam {days} hari dan 1 jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_DAY_HOUR": "Sesi ini akan kedaluwarsa dalam 1 hari dan 1 jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_HOURS": "Sesi ini akan kedaluwarsa dalam {hours} jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_HOURS_SINGULAR": "Sesi ini akan kedaluwarsa dalam 1 jam \u2014 semua file akan dihapus.",
    "SESSION_EXPIRY_CAPTION_SOON": "Sesi ini akan segera kedaluwarsa \u2014 semua file akan dihapus.",
    "SESSION_CREATE_BUTTON_TOOLTIP": "Buat sesi terpisah (hasil saat ini tetap tersimpan)",
    "SESSION_LOAD_BUTTON_TOOLTIP": "Muat sesi yang ada berdasarkan ID",
    "SESSION_EXTEND_BUTTON_TOOLTIP": "Perpanjang sesi — memberikan hingga 7 hari dari sekarang",
    "PROGRESS_HEADER": "⏳ Progres",
    "PROGRESS_CAPTION": "Pantau aktivitas crawl secara langsung.",
    "PROGRESS_EXPANDER_LABEL": "Statistik langsung",
    "PROGRESS_EXPANDER_LABEL_ACTIVE": "Statistik langsung: {crawl_id}",
    "LANG_SELECTOR_LABEL": "Bahasa",
    "NAV_CRAWL": "1. Crawl",
    "NAV_VECTOR_INDEX": "2. Vector Index",
    "NAV_SEMANTIC_SEARCH": "3. Semantic Search",
    "NAV_BASIC_RAG_QA": "4. RAG Q&A Sederhana",
    "NAV_CONVERSATIONAL_RAG": "5. Conversational RAG",
    "PAGE_VECTOR_INDEX_TITLE": ":material/settings: Langkah 2 - Bangun Vector Index",
    "PAGE_VECTOR_INDEX_SUBTITLE": (
        "Ubah halaman hasil crawl dan dokumen Anda sendiri menjadi vector database yang "
        "dapat dicari untuk retrieval-augmented generation."
    ),
    "PAGE_SEMANTIC_SEARCH_TITLE": ":material/search: Langkah 3 - Semantic Search",
    "PAGE_SEMANTIC_SEARCH_SUBTITLE": (
        "Pilih vector database dari koleksi terindeks Anda, masukkan kueri pencarian atau "
        "embedding, dan segera ambil chunk yang paling mirip berdasarkan semantic similarity."
    ),
    "PAGE_BASIC_RAG_QA_TITLE": ":material/question_answer: Langkah 4 - RAG Q&A Sederhana",
    "PAGE_BASIC_RAG_QA_SUBTITLE": (
        "Ambil pengetahuan dengan semantic search, susun prompt yang berlandaskan konteks, "
        "lalu panggil language model untuk menghasilkan jawaban dari pengetahuan tersebut."
    ),
    "PAGE_CONVERSATIONAL_RAG_TITLE": ":material/forum: Langkah 5 - Conversational RAG",
    "PAGE_CONVERSATIONAL_RAG_SUBTITLE": (
        "Adakan percakapan multi-giliran dengan dokumen Anda. Aplikasi secara otomatis menulis "
        "ulang pertanyaan lanjutan menggunakan konteks percakapan, mengambil pengetahuan segar "
        "untuk setiap giliran, dan mempertahankan riwayat selama chat."
    ),
    "PLACEHOLDER_SECTION_HEADER": "Area kerja langkah",
    "PLACEHOLDER_SECTION_CAPTION": (
        "Halaman ini memakai kontrol sesi dan layout yang sama sambil backend RAG ditambahkan."
    ),
    "PLACEHOLDER_EXPANDER_LABEL": "Ringkasan kebutuhan",
    "PLACEHOLDER_VECTOR_INDEX": (
        "Pilih file Markdown atau teks yang dihasilkan, termasuk arsip ZIP yang berisi file "
        "tersebut. Alur berikutnya akan memecah konten menjadi chunk, membuat embedding, "
        "dan menyimpan index di ChromaDB."
    ),
    "PLACEHOLDER_SEMANTIC_SEARCH": (
        "Masukkan kueri pencarian, buat embedding dengan model yang sama seperti chunk dalam "
        "index, jalankan similarity search, lalu tampilkan snippet berperingkat dengan skor "
        "dan referensi sumber."
    ),
    "PLACEHOLDER_BASIC_RAG_QA": (
        "Ajukan satu pertanyaan, ambil chunk yang paling relevan, gabungkan ke dalam prompt, "
        "panggil LLM yang dipilih, lalu tampilkan jawaban bersama sumber konteks."
    ),
    "PLACEHOLDER_CONVERSATIONAL_RAG": (
        "Gunakan antarmuka chat yang dapat menulis ulang kueri retrieval dari konteks "
        "percakapan, menyertakan riwayat pesan terbaru, dan berkembang menjadi alur RAG "
        "dengan memory."
    ),
    # ── RAG pages (Steps 3-5) ──────────────────────────────────
    "RAG_NO_INDEX_HINT": "Belum ada vector index. Bangun satu di Langkah 2 dulu.",
    "RAG_INDEX_LABEL": "Vector index",
    "RAG_INDEX_HELP": "Pilih index hasil Langkah 2 yang akan dikueri.",
    "RAG_INDEX_OPTION": "{folder} / {run} · {model} · {chunks} chunk",
    "RAG_LLM_LABEL": "Model jawaban",
    "RAG_LLM_HELP": (
        "Model chat yang menulis jawaban. Model cloud (☁️‣🔑) memerlukan API key di "
        "file konfigurasi — lihat README untuk cara mengaturnya. Jika tidak tersedia, "
        "aplikasi memakai model echo offline."
    ),
    "RAG_LLM_TAG_OFFLINE": "💻 Offline (echo)",
    "RAG_LLM_TAG_CLOUD": "☁️‣🔑",
    "RAG_LLM_SIZE_SMALL": "Kecil",
    "RAG_LLM_SIZE_MEDIUM": "Sedang",
    "RAG_LLM_SIZE_LARGE": "Besar",
    "RAG_LLM_INDICATOR_OFFLINE": (
        "Berjalan offline dan mengulang pertanyaan alih-alih membuat jawaban. Gunakan "
        "untuk mencoba alur tanpa kredensial."
    ),
    "RAG_LLM_INDICATOR_CLOUD": (
        "Berjalan di cloud. Perlu API key atau kredensial yang dikonfigurasi di server."
    ),
    "RAG_TOP_K_LABEL": "Chunk",
    "RAG_TOP_K_HELP": "Berapa banyak chunk paling mirip yang diambil sebagai konteks.",
    "RAG_SOURCES_HEADER": "Sumber",
    "RAG_SOURCE_CAPTION": "{source} · skor {score}",
    "RAG_MODEL_USED_CAPTION": "Dijawab dengan: {model}",
    "RAG_GENERATING": "Membuat jawaban…",
    "SEARCH_SECTION_HEADER": "🔍 Cari di index Anda",
    "SEARCH_SECTION_CAPTION": (
        "Temukan chunk yang paling mirip dengan kueri, lengkap dengan skor relevansi dan sumber."
    ),
    "SEARCH_QUERY_LABEL": "Kueri pencarian",
    "SEARCH_QUERY_PLACEHOLDER": "Ketik yang Anda cari…",
    "SEARCH_BUTTON": "Cari",
    "SEARCH_SEARCHING": "Mencari…",
    "SEARCH_RESULTS_EXPANDER": ":material/leaderboard: Hasil pencarian • Top {count} kecocokan berdasarkan kemiripan",
    "SEARCH_RESULTS_PANEL": ":material/leaderboard: Hasil pencarian",
    "SEARCH_NO_RESULTS": "Tidak ada chunk yang cocok untuk kueri ini.",
    "SEARCH_RESULTS_EMPTY": "Jalankan pencarian untuk melihat chunk yang cocok di sini.",
    "SEARCH_META_HEADER": ":material/info: Metadata",
    "SEARCH_META_CREATED": "Dibuat",
    "SEARCH_META_MODEL": "Model embedding",
    "SEARCH_META_LANGUAGE": "Bahasa",
    "SEARCH_META_FILES": "File",
    "SEARCH_META_DIMENSION_CHUNKS": "Dimensi / Chunk",
    "SEARCH_META_CHUNK_SIZE_OVERLAP": "Ukuran / overlap chunk",
    "SEARCH_META_SKIPPED": "Berkas dilewati",
    "SEARCH_META_COLLECTION": "Koleksi",
    "SEARCH_TOP_N_LABEL": "Hasil teratas",
    "SEARCH_TOP_N_HELP": (
        "Berapa banyak chunk yang cocok untuk ditampilkan, skor tertinggi dulu. Lebih sedikit "
        "(3-5) membuat pembacaan cepat dan fokus; lebih banyak (10+) memperluas cakupan tetapi "
        "menambah yang harus ditinjau. Mulai dari sekitar 5."
    ),
    "SEARCH_RESULT_HEADER": "#{rank} · {source}",
    "SEARCH_RESULT_SIMILARITY": "Kemiripan",
    "SEARCH_RESULT_TAB_PREVIEW": "Pratinjau",
    "SEARCH_RESULT_TAB_RAW": "Mentah",
    "SEARCH_RESULT_ID": "Chunk {id}",
    "SEARCH_RESULT_SIZE": "{size} karakter",
    "SEARCH_RESULT_LANGUAGE": "Bahasa {language}",
    "SEARCH_HISTORY_EXPANDER": ":material/history: Riwayat pencarian",
    "SEARCH_HISTORY_EMPTY": "Belum ada pencarian — jalankan pencarian untuk membangun riwayat.",
    "SEARCH_HISTORY_RESULT_COUNT": "{n} hasil",
    "SEARCH_HISTORY_REPLAY_HELP": "Cari kueri ini lagi",
    "SEARCH_HISTORY_PIN_HELP": "Sematkan ke atas",
    "SEARCH_HISTORY_UNPIN_HELP": "Lepas sematan",
    "SEARCH_HISTORY_INDEX_GONE": "Vector database tersebut sudah tidak ada — pilih index lain.",
    "SEARCH_HISTORY_LABEL_QUERY": "Pertanyaan",
    "SEARCH_HISTORY_LABEL_TIME": "Dicari",
    "SEARCH_HISTORY_LABEL_RESULTS": "Hasil",
    "SEARCH_HISTORY_LABEL_INDEX_NAME": "Nama indeks",
    "SEARCH_HISTORY_LABEL_INDEX_DATE": "Tanggal waktu indeks",
    "SEARCH_HISTORY_LABEL_DETAILS": ":material/info: Metadata",
    "BASIC_QA_SECTION_HEADER": ":material/quiz: Tanya & hasilkan",
    "BASIC_QA_SECTION_CAPTION": (
        "Cari pengetahuan di indeks Anda, susun prompt, dan hasilkan jawaban yang "
        "berlandaskan konteks."
    ),
    "BASIC_QA_LLM_LABEL": "Model bahasa",
    "BASIC_QA_LLM_HELP": (
        "Model bahasa yang membaca prompt dan menulis jawaban. Model cloud (☁️‣🔑) "
        "memerlukan API key di file konfigurasi — lihat README untuk cara mengaturnya. "
        "Tanpa itu aplikasi beralih ke model echo offline."
    ),
    "BASIC_QA_TOP_RESULTS_LABEL": "Hasil teratas",
    "BASIC_QA_TOP_RESULTS_HELP": (
        "Berapa banyak chunk top-N dari semantic search — dengan skor kemiripan tertinggi "
        "— yang diambil sebagai pengetahuan untuk jawaban."
    ),
    "BASIC_QA_TONE_LABEL": "Nada",
    "BASIC_QA_TONE_HELP": "Gaya penulisan yang digunakan model saat menjawab.",
    "BASIC_QA_QUESTION_LABEL": "Pertanyaan Anda",
    "BASIC_QA_QUESTION_PLACEHOLDER": "Ajukan pertanyaan tentang dokumen yang terindeks…",
    "BASIC_QA_GENERATE_BUTTON": "Hasilkan prompt",
    "BASIC_QA_GENERATE_HELP": (
        "Jalankan semantic search dan susun prompt RAG dari pertanyaan, pengetahuan yang "
        "diambil, dan nada."
    ),
    "BASIC_QA_SEARCHING": "Mencari di indeks Anda…",
    "BASIC_QA_RESULTS_EMPTY": "Hasilkan prompt untuk mencari di indeks Anda dan melihat kecocokannya di sini.",
    "BASIC_QA_PROMPT_LABEL": "Prompt",
    "BASIC_QA_PROMPT_PLACEHOLDER": "Hasilkan prompt untuk melihatnya di sini — lalu sunting bila perlu dan kirim.",
    "BASIC_QA_PROMPT_HELP": (
        "Prompt lengkap yang dikirim ke model. Sunting bebas, lalu Kirim (atau tekan "
        "Ctrl/Cmd+Enter)."
    ),
    "BASIC_QA_SEND_BUTTON": "Kirim",
    "BASIC_QA_SEND_HELP": "Kirim prompt ke model bahasa terpilih dan streaming jawabannya.",
    "BASIC_QA_MAXIMIZE_HELP": "Perbesar editor prompt",
    "BASIC_QA_MAXIMIZE_TITLE": "Sunting prompt",
    "BASIC_QA_MAXIMIZE_APPLY": "Terapkan",
    "BASIC_QA_EDIT_TEMPLATE_BUTTON": "Sunting templat",
    "BASIC_QA_EDIT_TEMPLATE_HELP": (
        "Sunting templat prompt yang diisi oleh Hasilkan prompt. Disimpan untuk sesi ini."
    ),
    "BASIC_QA_EDIT_TEMPLATE_TITLE": "Sunting templat prompt",
    "BASIC_QA_EDIT_TEMPLATE_CAPTION": (
        "Pertahankan placeholder {question}, {start}, {knowledge}, {end}, dan {tone}. "
        "Disimpan untuk sesi ini; Atur ulang mengembalikan default."
    ),
    "BASIC_QA_EDIT_TEMPLATE_SAVE": "Simpan",
    "BASIC_QA_EDIT_TEMPLATE_RESET": "Atur ulang ke default",
    "BASIC_QA_EDIT_TEMPLATE_INVALID": (
        "Pertahankan hanya placeholder {question}, {start}, {knowledge}, {end}, dan {tone} — "
        "hapus teks lain dalam kurung kurawal, lalu simpan lagi."
    ),
    "BASIC_QA_NO_PROMPT_HINT": "Hasilkan prompt terlebih dahulu, lalu kirim.",
    "BASIC_QA_ANSWER_HEADER": ":material/smart_toy: Jawaban",
    "BASIC_QA_ANSWER_STATS": (
        "Model — {model} · Token — input {input} · output {output} · "
        "total {total} · dijawab dalam {seconds}s"
    ),
    "BASIC_QA_TOKEN_NA": "n/a",
    "BASIC_QA_TOKEN_PANEL_TITLE": "Jumlah token",
    "BASIC_QA_SUMMARY_QUOTA_LABEL": "Kuota",
    "BASIC_QA_SUMMARY_USAGE_LABEL": "% Pemakaian",
    "BASIC_QA_SUMMARY_INPUT_LABEL": "Input",
    "BASIC_QA_SUMMARY_OUTPUT_LABEL": "Output",
    "BASIC_QA_SUMMARY_TOTAL_LABEL": "Total",
    "BASIC_QA_HISTORY_EXPANDER": ":material/history: Riwayat prompt",
    "BASIC_QA_HISTORY_EMPTY": "Belum ada prompt — kirim satu untuk membangun riwayat Anda.",
    "BASIC_QA_HISTORY_REPLAY_HELP": "Muat prompt ini kembali ke formulir",
    "BASIC_QA_HISTORY_PIN_HELP": "Sematkan ke atas",
    "BASIC_QA_HISTORY_UNPIN_HELP": "Lepas sematan",
    "BASIC_QA_HISTORY_LABEL_QUESTION": "Pertanyaan",
    "BASIC_QA_HISTORY_LABEL_TIME": "Waktu",
    "BASIC_QA_HISTORY_DETAILS_EXPANDER": ":material/info: Metadata",
    "BASIC_QA_HISTORY_PROMPT_EXPANDER": ":material/description: Prompt",
    "BASIC_QA_HISTORY_ANSWER_EXPANDER": ":material/forum: Jawaban",
    "BASIC_QA_HISTORY_META_INDEX_NAME": "Nama indeks",
    "BASIC_QA_HISTORY_META_INDEX_DATE": "Tanggal waktu indeks",
    "BASIC_QA_HISTORY_META_MODEL": "Model",
    "BASIC_QA_HISTORY_META_TONE": "Nada",
    "BASIC_QA_HISTORY_META_TOP": "Hasil teratas",
    "BASIC_QA_HISTORY_META_TOKENS": "Token",
    "BASIC_QA_HISTORY_META_TIME": "Waktu respons",
    "BASIC_QA_HISTORY_TOKENS_VALUE": "{input} in · {output} out · {total} total",
    "BASIC_QA_HISTORY_SECONDS": "{seconds}s",
    "CHAT_SECTION_HEADER": "💬 Mengobrol dengan dokumen Anda",
    "CHAT_SECTION_CAPTION": (
        "Ajukan pertanyaan lanjutan; aplikasi menulis ulang dengan konteks percakapan dan "
        "mengambil konteks baru tiap giliran."
    ),
    "CHAT_INPUT_PLACEHOLDER": "Ajukan pertanyaan…",
    "CHAT_CLEAR_BUTTON": "Hapus percakapan",
    "CHAT_EMPTY_HINT": "Mulai percakapan dengan mengajukan pertanyaan di bawah.",
    # ── Form ──────────────────────────────────────────────────────────────
    "FORM_SUBHEADER": "⚙️ Atur crawl Anda",
    "FORM_CAPTION": (
        "Konfigurasikan URL awal, aturan pemfilteran, dan perilaku crawl sebelum memulai."
    ),
    "FORM_EXPANDER_LABEL": "Pengaturan crawl",
    "FORM_URLS_LABEL": "URL Situs Web",
    "FORM_URLS_HELP": (
        "Tempel satu atau lebih halaman awal. "
        "Gunakan satu baris per situs atau pisahkan dengan koma."
    ),
    "FORM_INCLUDE_PATHS_LABEL": "Hanya sertakan pola URL",
    "FORM_INCLUDE_PATHS_HELP": (
        "Biarkan kosong untuk mengizinkan semua halaman di situs yang sama. "
        "Gunakan pola regex untuk tetap di dalam sebuah bagian."
    ),
    "FORM_EXCLUDE_PATHS_LABEL": "Lewati pola URL",
    "FORM_EXCLUDE_PATHS_HELP": "Halaman yang cocok dengan pola regex ini akan dilewati.",
    "FORM_LIMIT_LABEL": "Batas halaman",
    "FORM_LIMIT_HELP": (
        "Batas penemuan: setelah sejumlah halaman ditemukan, "
        "perayap berhenti menemukan tautan baru tetapi tetap menyelesaikan "
        "semua halaman yang sudah ditemukan."
    ),
    "FORM_DELAY_LABEL": "Jeda antar halaman",
    "FORM_DELAY_HELP": "Memberi jarak awal halaman untuk mengurangi pemblokiran oleh situs web.",
    "FORM_DEPTH_LABEL": "Kedalaman tautan",
    "FORM_DEPTH_HELP": "Seberapa dalam mengikuti tautan.",
    "FORM_RETRIES_LABEL": "Putaran percobaan ulang",
    "FORM_RETRIES_HELP": "Mencoba lagi halaman yang gagal setelah pendinginan.",
    "FORM_OUTPUT_FORMAT_LABEL": "Format keluaran",
    "FORM_OUTPUT_FORMAT_HELP": "Pilih Markdown untuk teks berformat atau TXT untuk teks biasa.",
    "FORM_EXTRACT_MAIN_LABEL": "Ekstrak hanya konten utama",
    "FORM_EXTRACT_MAIN_HELP": (
        "Menyimpan teks artikel/produk dan menghapus sebagian besar menu, footer, dan sidebar."
    ),
    "FORM_ADVANCED_LABEL": "Opsi lanjutan",
    "FORM_FLUSH_LABEL": "Tulis setiap N halaman",
    "FORM_FLUSH_HELP": "Menulis file yang dihasilkan secara berkala selama crawl.",
    "FORM_MAX_FILE_SIZE_LABEL": "Ukuran file maksimum (MB)",
    "FORM_MAX_FILE_SIZE_HELP": "Membagi keluaran menjadi file yang lebih mudah dibuka dan diunduh.",
    "FORM_WAIT_FOR_LABEL": "Tunggu render tambahan",
    "FORM_WAIT_FOR_HELP": ("Membantu halaman berat JavaScript selesai dimuat sebelum ekstraksi."),
    "FORM_TIMEOUT_LABEL": "Batas waktu halaman",
    "FORM_TIMEOUT_HELP": "Maksimum detik untuk memuat satu halaman.",
    "FORM_ACTIVITY_LOG_LABEL": "Entri log aktivitas",
    "FORM_ACTIVITY_LOG_HELP": (
        "Mengontrol berapa banyak entri terbaru yang ditampilkan di panel Log Aktivitas."
    ),
    "FORM_MAX_CONCURRENT_LABEL": "Pengambilan paralel",
    "FORM_MAX_CONCURRENT_HELP": (
        "Mengambil hingga N halaman yang sudah ditemukan secara bersamaan pada "
        "crawl awal. 5 (default) dapat mempercepat crawl besar pada situs yang "
        "permisif. Gunakan 1 untuk situs yang ketat atau mudah terkena batas "
        "laju. Jeda tetap memberi jarak awal "
        "permintaan; retry tetap serial demi keamanan WAF. Risiko: nilai lebih "
        "tinggi meningkatkan kemungkinan dibatasi kecepatannya atau diblokir. "
        "Minimum: 1. Direkomendasikan: 1-5."
    ),
    "FORM_EXCLUDE_TAGS_LABEL": "Tag HTML yang dihapus",
    "FORM_EXCLUDE_TAGS_HELP": (
        "Nilai umum menghapus menu, skrip, formulir, dan gaya dari teks yang diekstrak."
    ),
    "FORM_INCLUDE_ONLY_TAGS_LABEL": "Hanya simpan tag HTML ini",
    "FORM_INCLUDE_ONLY_TAGS_HELP": (
        "Lanjutan: hanya ekstrak konten dari tag HTML ini. Biarkan kosong untuk penggunaan normal."
    ),
    # ── Action buttons ────────────────────────────────────────────────────
    "BTN_START": "Mulai",
    "BTN_STOP": "Hentikan",
    # ── Stop dialog ───────────────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    "DIALOG_STOP_BODY": (
        "Hentikan crawl ini sekarang? Ini akan membatalkan halaman yang masih dalam proses."
    ),
    "DIALOG_BTN_KEEP": "Lanjutkan",
    "DIALOG_BTN_STOP": "Hentikan crawl",
    # Vector-indexing stop dialog (reuses DIALOG_BTN_KEEP for "Keep running").
    "VEC_DIALOG_STOP_BODY": (
        "Hentikan pengindeksan sekarang? Ini akan membatalkan dokumen yang masih diproses."
    ),
    "VEC_DIALOG_BTN_STOP": "Hentikan pengindeksan",
    # ── Load session dialog ───────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    "DIALOG_LOAD_SESSION_ID_LABEL": "ID Sesi",
    "DIALOG_LOAD_SESSION_ID_PLACEHOLDER": "Tempel ID sesi di sini",
    "DIALOG_LOAD_SESSION_ID_HELP": "Masukkan ID sesi dari browser atau komputer lain",
    "DIALOG_LOAD_BTN_CANCEL": "Batal",
    "DIALOG_LOAD_BTN_LOAD": "Muat",
    "DIALOG_LOAD_SESSION_NOT_FOUND": "Sesi '{id}' tidak ditemukan di server ini.",
    "DIALOG_LOAD_SESSION_ALREADY_LOADED": "Sesi '{id}' sudah tersedia. Beralih ke sesi tersebut.",
    "DIALOG_LOAD_SESSION_INVALID_ID": "ID sesi tidak valid.",
    # ── Toast messages ────────────────────────────────────────────────────
    "TOAST_SUCCESS": "{n} halaman berhasil di-crawl",
    "TOAST_FAILED": "{n} halaman gagal di-crawl",
    "TOAST_DISCOVERED": "{n} halaman ditemukan",
    "TOAST_SESSION_CREATED": "Sesi baru berhasil dibuat",
    "TOAST_SESSION_LOADED": "Sesi '{id}' berhasil dimuat.",
    "TOAST_SESSION_EXTENDED": "Sesi diperpanjang — masa berlaku diperbarui ke 7 hari",
    "TOAST_SESSION_EXTEND_FAILED": "Sesi gagal diperpanjang",
    # ── Progress metrics ──────────────────────────────────────────────────
    "METRIC_PROCESSED_LABEL": "📄 Upaya halaman",
    "METRIC_PROCESSED_DELTA": "{n} total",
    "METRIC_PROCESSED_DELTA_RETRY": "{n} upaya retry",
    "METRIC_PROCESSED_TOOLTIP": (
        "Jumlah upaya saat ini untuk fase crawl yang berjalan. Halaman gagal dapat dicoba lagi selama retry."
    ),
    "METRIC_SUCCESSFUL_LABEL": "✅ Berhasil",
    "METRIC_SUCCESSFUL_DELTA": "{n} selesai",
    "METRIC_SUCCESSFUL_TOOLTIP": "Halaman yang berhasil diproses",
    "METRIC_FAILED_LABEL": "❌ Gagal",
    "METRIC_FAILED_DELTA": "{n} gagal",
    "METRIC_FAILED_TOOLTIP": "Halaman yang gagal selama pemrosesan",
    "METRIC_DISCOVERED_LABEL": "🔎 Ditemukan",
    "METRIC_DISCOVERED_DELTA": "{n} ditemukan, {m} tersisa",
    "METRIC_DISCOVERED_TOOLTIP": "URL yang ditemukan dan diantrekan sejauh ini",
    "METRIC_LIMIT_LABEL": "🔢 Batas",
    "METRIC_LIMIT_TOOLTIP": (
        "Batas penemuan — setelah tercapai, URL baru tidak ditambahkan, "
        "tetapi URL yang sudah ditemukan tetap di-crawl."
    ),
    "METRIC_LIMIT_DELTA_REACHED": "Penemuan dihentikan (batas tercapai)",
    "METRIC_LIMIT_DELTA_MORE": "Menemukan lebih banyak halaman",
    "METRIC_STATE_WORD": "Status",
    "METRIC_STATE_DELTA": "Tahap siklus saat ini",
    "METRIC_STATE_TOOLTIP": "Status siklus hidup crawl saat ini",
    # ── Progress bar labels ───────────────────────────────────────────────
    "DENOM_DISCOVERED": "{n} ditemukan",
    "DENOM_LIMIT": "{n} batas",
    "PROGRESS_ATTEMPTS": "{n} upaya",
    "PROGRESS_COMPLETE": "selesai",
    "PROGRESS_RETRYING": "Sedang retry halaman gagal",
    # ── Progress charts ───────────────────────────────────────────────────
    "CHART_CUMULATIVE_TITLE_SECOND": "Total crawl per detik",
    "CHART_CUMULATIVE_TITLE_MINUTE": "Linimasa kemajuan crawl",
    "CHART_CUMULATIVE_TITLE_HOUR": "Total crawl per jam",
    "CHART_SERIES_LIMIT": "Batas",
    "CHART_SERIES_DISCOVERED": "Ditemukan",
    "CHART_SERIES_SUCCESSFUL": "Berhasil",
    "CHART_SERIES_FAILED": "Gagal",
    "CHART_TIME_UNIT_SECOND": "detik",
    "CHART_TIME_UNIT_MINUTE": "menit",
    "CHART_TIME_UNIT_HOUR": "jam",
    # ── Status line ───────────────────────────────────────────────────────
    "STATUS_CRAWLING": "Merayapi: {url_html}",
    "STATUS_ELAPSED": "Waktu berlalu: {elapsed}",
    "STATUS_NEXT_URL": "Berikutnya: {url_html}",
    "STATUS_ACTIVE_FETCHES": "Pengambilan aktif ({count} dari {max} dikonfigurasi)",
    "STATUS_NEXT_FETCHES": "Berikutnya ({count})",
    "STATUS_MORE_URLS": "+{count} lainnya",
    # ── ETA phrases ───────────────────────────────────────────────────────
    "ETA_ESTIMATING": "Mengestimasi...",
    "ETA_LESS_THAN_MINUTE": "Kurang dari satu menit lagi",
    "ETA_MINUTES": "Sekitar {n} menit lagi",
    "ETA_HOURS_MINUTES": "Sekitar {h}j {m}m lagi",
    # ── State banners ─────────────────────────────────────────────────────
    "BANNER_FAILED": "🔴 Gagal — pemrosesan mengalami kesalahan",
    "BANNER_CANCEL_REQUESTED": "🟡 Penghentian diminta — menunggu worker selesai",
    "BANNER_STOPPED": "🟡 Dihentikan — file yang dihasilkan tetap tersedia",
    # ── Error messages ────────────────────────────────────────────────────
    "ERROR_NO_ACTIVE_CRAWL": "Tidak ada crawl yang aktif untuk dihentikan.",
    "ERROR_CRAWL_ALREADY_RUNNING": "Crawl sudah berjalan di sesi browser ini.",
    "ERROR_SESSION_STORAGE_WRITE": (
        "Penyimpanan browser tidak tersedia. Aktifkan local storage di browser ini lalu "
        "muat ulang halaman."
    ),
    "ERROR_CRAWL_FAILED_FALLBACK": "Crawl gagal.",
    # ── Activity log ──────────────────────────────────────────────────────
    "ACTIVITY_LOG_HEADER": "Log aktivitas",
    # ── Files section ─────────────────────────────────────────────────────
    "FILES_HEADER": "Detail File",
    "FILES_CRAWL_RESULT_LABEL": "📁 Berkas & folder",
    "FILES_DOWNLOADS_SUBHEADER": "🗂️ File Output",
    "FILES_COL_NAME": "File",
    "FILES_COL_TYPE": "Tipe",
    "FILES_COL_SIZE": "Ukuran (MB)",
    "FILES_COL_MODIFIED": "Dimodifikasi",
    "FILES_DOWNLOAD_TOO_LARGE": "{file} terlalu besar untuk diunduh dari aplikasi.",
    "FILES_EXPLORE_3D_LABEL": "Jelajahi dalam 3D",
    "FILES_EXPLORE_3D_HELP": "Jelajahi halaman hasil crawl sebagai jagat 3D interaktif (membuka tab baru)",
    "FILES_DOWNLOADS_IN_PROGRESS": "Crawl sedang berjalan — file muncul seiring halaman diproses.",
    "FILES_DOWNLOADS_SUBTITLE": "Pratinjau atau unduh file crawl Anda di bawah ini.",
    "FILES_PREVIEW_BUTTON": ":material/visibility:",
    "FILES_PREVIEW_HELP": "Pratinjau {file}",
    "FILES_PREVIEW_PATH": "Path: {path}",
    "FILES_PREVIEW_SIZE": "Ukuran: {size_kib} KiB",
    "FILES_PREVIEW_MODIFIED_AT": "Terakhir dimodifikasi: {value}",
    "FILES_PREVIEW_CREATED_AT": "Dibuat: {value}",
    "FILES_PREVIEW_UNSUPPORTED": "Pratinjau hanya tersedia untuk file berbasis teks. {file} tidak bisa dipratinjau.",
    "FILES_PREVIEW_MISSING": "File yang dipilih sudah tidak tersedia: {file}",
    "FILES_PREVIEW_READ_ERROR": "Tidak dapat membaca file untuk pratinjau: {file}",
    "FILES_PREVIEW_EMPTY": "{file} kosong.",
    "FILES_PREVIEW_TRUNCATED": "Pratinjau dibatasi pada {limit_kib} KiB pertama.",
    "FILES_DELETE_DIALOG_CANCEL": "Simpan",
    "FILES_DOWNLOAD_ZIP_BUTTON": ":material/download: Ekspor",
    "FILES_DOWNLOAD_ZIP_HELP": "Ekspor folder {folder} sebagai zip bertanda tangan yang bisa diimpor di instance lain",
    "FILES_DOWNLOAD_ZIP_TOO_LARGE": "Folder {folder} terlalu besar untuk diekspor sebagai zip.",
    "FILES_EXPORT_PREPARING": "Menyiapkan ekspor {folder}\u2026",
    "FILES_EXPORT_DOWNLOAD_STARTED": "Unduhan akan dimulai otomatis \u2014 gunakan tombol di atas jika tidak.",
    "FILES_DELETE_FOLDER_BUTTON": "Hapus folder ini",
    "FILES_DELETE_FOLDER_HELP": "Hapus permanen folder {folder} dan semua isinya.",
    "FILES_DELETE_FOLDER_DIALOG_TITLE": "Hapus folder?",
    "FILES_DELETE_FOLDER_DIALOG_BODY": (
        "Hapus permanen **{folder}** dan semua berkas di dalamnya? Tindakan ini tidak "
        "bisa dibatalkan — pastikan Anda sudah mengunduh yang ingin disimpan."
    ),
    "FILES_DELETE_FOLDER_DIALOG_CONFIRM": "Hapus folder",
    "FILES_UPLOAD_BUTTON": ":material/upload: Impor",
    "FILES_UPLOAD_BUTTON_HELP": "Impor zip folder yang diekspor dari aplikasi ini",
    "FILES_UPLOAD_DIALOG_TITLE": "Unggah zip folder",
    "FILES_UPLOAD_PROMPT": "Pilih zip yang Anda unduh dari Berkas Keluaran aplikasi ini.",
    "FILES_UPLOAD_INVALID": (
        "Zip ini tidak bisa diunggah. Gunakan zip yang diunduh dari instance aplikasi dengan "
        "kunci yang sama, tanpa perubahan — unduh ulang lalu coba lagi."
    ),
    "FILES_UPLOAD_CONFIRM_BODY": (
        "Terverifikasi. Agar tidak bentrok dengan folder yang ada, akan ditambahkan sebagai "
        "**{folder}**. Lanjutkan?"
    ),
    "FILES_UPLOAD_CONFIRM": "Unggah",
    "FILES_UPLOAD_CANCEL": "Batal",
    "FILES_UPLOAD_SUCCESS": "Unggahan selesai — menambahkan {folder}.",  # ── Ready result download ──────────────────────────────────────────
    "READY_RESULT_HEADER": "📦 Hasil crawl siap",
    "READY_RESULT_SINGLE_SUBTITLE": "1 file berhasil siap diunduh",
    "READY_RESULT_ZIP_SUBTITLE": "{count} file berhasil — dikemas dalam satu zip",
    "READY_RESULT_DOWNLOAD_BUTTON": "⬇ Unduh",
    "READY_RESULT_TOO_LARGE": "Output terlalu besar untuk diunduh dari aplikasi — gunakan daftar file di bawah.",
    # ── Portfolio footer ─────────────────────────────────────────────────
    "FOOTER_BUILT_BY": "Dibuat oleh {author}",
    "FOOTER_TAGLINE": "Playground crawl-to-RAG dengan bantuan AI",
    "FOOTER_LINK_LINKEDIN": "LinkedIn",
    "FOOTER_LINK_GITHUB": "GitHub",
    "FOOTER_LINK_README": "Baca dokumentasi",
    "FOOTER_LINK_STREAMLIT_README": "Panduan app",
    # ── Portfolio modal ──────────────────────────────────────────────────
    "PORTFOLIO_MODAL_TITLE": "Hai, saya {author}",
    "PORTFOLIO_MODAL_BODY": (
        "Saya membangun proyek ini sebagai RAG playground berbasis eksperimen "
        "langsung dengan bantuan AI. Saat ini aplikasinya bisa meng-crawl situs "
        "web dan mengubah halaman menjadi Markdown yang rapi. Berikutnya, saya "
        "akan menambahkan vector embeddings, semantic search, tanya jawab RAG, "
        "dan eksperimen conversational RAG."
    ),
    "PORTFOLIO_MODAL_CTA": (
        "Kalau proyek ini menarik atau berguna, mari terhubung di LinkedIn atau "
        "beri star di repo GitHub. Saya senang berbagi progres dan bertukar catatan."
    ),
    "PORTFOLIO_MODAL_LINK_LINKEDIN": "Terhubung di LinkedIn",
    "PORTFOLIO_MODAL_LINK_GITHUB": "Beri star repo GitHub",
    "PORTFOLIO_MODAL_LINK_README": "Baca dokumentasi",
    "PORTFOLIO_MODAL_LINK_STREAMLIT_README": "Panduan developer app",
    "PORTFOLIO_MODAL_CLOSE_LABEL": "Tutup",
    "PORTFOLIO_MODAL_PHOTO_ALT": "Foto profil {author}",
    # ── Vector index (Step 2) ─────────────────────────────────────────────
    "VEC_SECTION_HEADER": ":material/database: Bangun basis pengetahuan yang dapat dicari",
    "VEC_SECTION_CAPTION": (
        "Pilih file sumber Anda, atur cara teks dipecah dan di-embed, lalu bangun vector "
        "database yang bisa Anda cari dan tanyakan."
    ),
    "VEC_SOURCES_LABEL": "File hasil crawl",
    "VEC_SOURCES_HELP": (
        "File Markdown, teks, atau ZIP dari Langkah 1. File ZIP hanya menyumbang anggota "
        ".md dan .txt."
    ),
    "VEC_SOURCES_EMPTY": "Belum ada hasil crawl. Jalankan Langkah 1 dahulu atau unggah file di bawah.",
    "VEC_UPLOAD_LABEL": "Unggah file",
    "VEC_UPLOAD_HELP": "Tambahkan file .md, .txt, atau .zip Anda untuk diindeks bersama hasil crawl.",
    "VEC_CHUNK_SIZE_LABEL": "Ukuran chunk",
    "VEC_CHUNK_SIZE_HELP": "Jumlah maksimum karakter atau token yang disimpan text splitter di setiap fragmen sebelum membuat embedding.",
    "VEC_CHUNK_OVERLAP_LABEL": "Tumpang tindih chunk",
    "VEC_CHUNK_OVERLAP_HELP": "Jumlah karakter atau token dari akhir satu chunk yang diulang di awal chunk berikutnya.",
    "VEC_WORKERS_LABEL": "Pekerja",
    "VEC_WORKERS_HELP": "Pekerja embedding paralel (1-8). Lebih banyak mempercepat model cloud pada crawl besar; model offline lokal selalu berjalan satu utas.",
    "VEC_EMBEDDING_MODEL_LABEL": "Model embedding",
    "VEC_EMBEDDING_MODEL_HELP": "Model yang mengubah teks menjadi vektor numerik yang dapat dicari. Model cloud (☁️‣🔑) memerlukan API key di file konfigurasi — lihat README untuk cara mengaturnya. Jika model yang dipilih tidak tersedia (kunci API, kredensial, atau internet tidak ada), pengindeksan berhenti dengan kesalahan dan Anda dapat beralih ke model lokal luring (all-MiniLM-L6-v2) yang tidak memerlukan penyiapan.",
    "VEC_MODEL_TAG_LOCAL": "💻 Lokal",
    "VEC_MODEL_TAG_CLOUD": "☁️‣🔑",
    "VEC_MODEL_INDICATOR_LOCAL": (
        "Berjalan di mesin ini. Mengunduh model sekali (sekitar 80 MB) saat pertama kali, "
        "lalu bekerja luring."
    ),
    "VEC_MODEL_INDICATOR_CLOUD": (
        "Berjalan di cloud. Perlu API key atau kredensial yang dikonfigurasi di server."
    ),
    "VEC_EMBEDDING_DIMENSION_LABEL": "Dimensi embedding",
    "VEC_EMBEDDING_DIMENSION_HELP": "Seberapa detail vektor embedding. Dimensi lebih besar menangkap lebih banyak detail, dimensi lebih kecil lebih ringan untuk disimpan dan dicari.",
    "VEC_LANGUAGE_LABEL": "Bahasa",
    "VEC_LANGUAGE_HELP": "Petunjuk bahasa sumber yang diberikan ke splitter atau lapisan embedding agar model multibahasa menangani tokenisasi dengan benar.",
    "VEC_ERROR_NO_INPUTS": "Pilih minimal satu hasil crawl atau unggah file sebelum mengindeks.",
    "VEC_ERROR_ALREADY_RUNNING": "Sebuah pekerjaan pengindeksan sedang berjalan.",
    "VEC_ERROR_NO_ACTIVE_INDEX": "Tidak ada pekerjaan pengindeksan aktif untuk dihentikan.",
    "VEC_PROGRESS_HEADER": "\u23f3 Progres pengindeksan",
    "VEC_STATUS_RUNNING": "Pengindeksan sedang berlangsung\u2026",
    "VEC_STATUS_CHUNKS": "Terindeks {processed} dari {total} chunk",
    "VEC_STAGE_RESOLVING_MODEL": "Menyiapkan model embedding\u2026",
    "VEC_STAGE_LOADING": "Memuat dokumen\u2026",
    "VEC_STAGE_CHUNKING": "Memecah teks menjadi chunk\u2026",
    "VEC_STAGE_EMBEDDING": "Meng-embed chunk\u2026",
    "VEC_STAGE_SAVING": "Menyimpan vector index\u2026",
    "VEC_RESULT_SUCCESS": "Pengindeksan selesai \u2014 {files} file, {chunks} chunk.",
    "VEC_RESULT_FAILED": "Pengindeksan gagal.",
    "VEC_RESULT_CANCELLED": "Pengindeksan dihentikan.",
    "VEC_RESULT_SKIPPED": "{count} file dilewati.",
    "VEC_RESULT_WARNINGS_LABEL": "Peringatan",
    "VEC_RESULT_ERRORS_LABEL": "Kesalahan",
    "VEC_ERROR_SSL_HINT": (
        "Ini tampak seperti masalah sertifikat jaringan saat pengunduhan model sekali "
        "pakai. Model lokal mengunduh sekali melalui internet. Di jaringan perusahaan, "
        "atur SSL_CERT_FILE atau REQUESTS_CA_BUNDLE ke berkas sertifikat organisasi Anda, "
        "atau jalankan sekali di jaringan tanpa batasan."
    ),
    "VEC_ERROR_OPENAI_KEY_HINT": (
        "Embedding OpenAI memerlukan kunci API. Setel OPENAI_API_KEY di berkas .env "
        "(atau environment) lalu mulai ulang aplikasi \u2014 atau pilih model offline "
        "lokal, yang tidak memerlukan kunci atau internet."
    ),
    "VEC_ERROR_AWS_CREDENTIALS_HINT": (
        "Embedding Amazon Titan memerlukan kredensial AWS. Setel AWS_ACCESS_KEY_ID, "
        "AWS_SECRET_ACCESS_KEY, dan AWS_REGION (atau AWS_PROFILE) di berkas .env lalu "
        "mulai ulang aplikasi \u2014 atau pilih model offline lokal, yang tidak "
        "memerlukan kredensial atau internet."
    ),
    "VEC_ERROR_EMBEDDING_FAILED_HINT": (
        "Layanan embedding tidak dapat dijangkau. Periksa koneksi internet serta proxy "
        "atau firewall, lalu coba lagi \u2014 atau pilih model offline lokal, yang "
        "berjalan tanpa internet."
    ),
    "VEC_ERROR_MODEL_UNAVAILABLE_HINT": (
        "Model embedding yang dipilih tidak tersedia. Pastikan paket penyedia dan "
        "kredensialnya terpasang serta terkonfigurasi \u2014 atau pilih model offline "
        "lokal, yang tidak memerlukan penyiapan."
    ),
    # ── State display labels ──────────────────────────────────────────────
    "STATE_LABELS": {
        "idle": "Siap",
        "running": "Berjalan",
        "failed": "Gagal",
        "completed": "Selesai",
        "cancel_requested": "Pembatalan Diminta",
        "stopped": "Dihentikan",
    },
    # ── Kode pesan library (terjemahan; kode yang tidak ada pakai teks library) ─
    "MESSAGE_CODES": {
        "crawl.browser_missing": (
            "Binari browser Playwright tidak ada di lingkungan Python ini. "
            "Instal Chromium lalu coba crawl lagi:\n"
            "playwright install --with-deps chromium"
        ),
        "crawl.engine_missing": (
            'Mesin crawler belum terpasang. Instal dengan: pip install "rag-playground[crawl]"'
        ),
        "crawl.ssl_certificate": (
            "Tidak dapat melakukan crawl karena sertifikat TLS/SSL tidak dapat "
            "diverifikasi: {detail}"
        ),
        "crawl.crawl_failed": "Crawl tidak dapat diselesaikan: {detail}",
        "crawl.ocr_unavailable": (
            "Sebagian halaman PDF berupa gambar hasil pindai, tetapi OCR tidak "
            "tersedia karena Tesseract belum terpasang, sehingga teks pada halaman "
            "tersebut tidak dapat diekstrak."
        ),
        "crawl.blocked_backoff": (
            "Situs tampaknya memblokir akses otomatis; "
            "berhenti sejenak sekitar {wait_seconds:.0f}d sebelum melanjutkan."
        ),
        "vector.missing_openai_key": ("Model embedding OpenAI memerlukan kunci API: {detail}"),
        "vector.missing_aws_credentials": (
            "Model embedding Amazon Titan memerlukan kredensial AWS: {detail}"
        ),
        "vector.dimension_mismatch": (
            "Dimensi embedding {requested_dimension} tidak didukung oleh "
            "{model!r}; menggunakan {actual_dimension}."
        ),
        "vector.no_readable_content": (
            "Tidak ada konten .md atau .txt yang dapat dibaca pada input yang dipilih."
        ),
        "vector.no_chunks": "Input yang dipilih tidak menghasilkan potongan teks untuk diindeks.",
        "vector.cancelled_partial": "Pengindeksan dibatalkan; hasil sebagian telah disimpan.",
        "vector.cancelled_before_chunking": ("Pengindeksan dibatalkan sebelum pemotongan dimulai."),
        "vector.skipped_unsupported_file": "Melewati berkas yang tidak didukung: {file}",
        "vector.file_unreadable": "Tidak dapat membaca {file}: {detail}",
        "vector.archive_unreadable": "Tidak dapat membaca arsip {file}: {detail}",
        "vector.archive_empty": "Tidak ada berkas .md atau .txt di {file}",
        "vector.ssl_certificate": (
            "Tidak dapat menjangkau layanan embedding karena sertifikat TLS/SSL-nya "
            "tidak dapat diverifikasi: {detail}"
        ),
        "vector.embedding_failed": "Embedding atau penyimpanan gagal: {detail}",
        "vector.model_unavailable": "Model embedding tidak tersedia: {detail}",
        "vector.chunking_failed": "Pemotongan gagal: {detail}",
    },
}
