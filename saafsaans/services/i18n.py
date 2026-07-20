"""Hindi copy, and the lookup that serves it.

Structure, and why this one
---------------------------
Every Hindi string in the application lives in this single file, grouped to
mirror the English sources it replaces, rather than sitting beside its English
twin in ``normalize.py``, ``risk.py``, ``presenters.py`` and ``advisories.py``.

The alternative -- a ``hi`` key next to every English string -- keeps a
translation physically next to its original, which is genuinely easier to keep
in sync while editing. It was rejected because of who has to read this next.
The translation is unreviewed, and the person who signs it off is a Hindi
speaker who is not necessarily a programmer. Asking them to review one file of
prose is a request somebody can actually complete. Asking them to review four
Python modules, finding the Hindi among the dictionaries and the scoring
tables, is a request that gets abandoned. The cost of that choice -- that a
change to an English string can silently orphan its translation -- is paid off
by ``test_every_translatable_string_has_a_hindi_counterpart``, which fails the
build when the two drift apart.

Nothing here is machine-translated at request time. These are committed
strings, so what ships is what was written and reviewed, and a network failure
cannot change the language a health instruction is given in.

Status: AWAITING REVIEW BY A HINDI SPEAKER. Drafted, not signed off. Every page
served with ``?lang=hi`` carries a banner saying so. A mistranslated
instruction about an inhaler is worse than English, which is why the banner is
a condition of shipping rather than a nicety.

What is NOT translated yet, and a Hindi reviewer will see it
------------------------------------------------------------
Three surfaces still render in English under the Hindi banner, because they are
assembled in Python rather than looked up as whole strings:

* the persona sentence ("an adult with asthma, planning outdoor exercise in
  Anand Vihar"), built piece by piece in ``presenters.persona_sentence``;
* the comparison line that explains the gap to a healthy adult;
* the risk driver chips.

Translating them needs those functions restructured to compose from translated
parts, which is a change to ``presenters.py`` rather than to this file. It is
listed here rather than left to be discovered, because the reviewer reading
this file is exactly the person who will notice and wonder whether it was
missed or decided.

Register: Hindi as a Delhi resident actually speaks it, not literal
translation. Where the English term is the one people use out loud -- AQI,
PM2.5, N95, COPD -- it stays in Latin script inside the Devanagari, because
transliterating it would make it harder to recognise, not easier.
"""

LANGUAGES = ("en", "hi")
DEFAULT_LANG = "en"

# Shown on every page when Hindi is active. Not dismissible: it is a statement
# about the reliability of the health advice on the page, and a reader who
# dismissed it would go on reading unreviewed medical instructions.
REVIEW_BANNER = (
    "यह हिंदी अनुवाद अभी किसी हिंदी बोलने वाले द्वारा जाँचा नहीं गया है। "
    "दवा या इनहेलर से जुड़ी कोई भी बात अंग्रेज़ी में दोबारा पढ़ लें।"
)
REVIEW_BANNER_EN = (
    "This Hindi translation has not yet been checked by a Hindi speaker. "
    "For anything about medicines or an inhaler, please read it in English too."
)


def normalise(value: str) -> str:
    """The language for a request. Anything unrecognised falls back to English.

    A wrong language code must never produce a blank page or a half-translated
    one; English is always a complete, reviewed answer.
    """
    return value if value in LANGUAGES else DEFAULT_LANG


def t(lang: str, group: str, key: str, english: str) -> str:
    """Hindi for ``group``/``key`` when asked for and present, else the English.

    Falls back per string rather than per page: a missing translation shows one
    English sentence among the Hindi, which is survivable, instead of raising
    or rendering an empty element, which is not. The completeness test exists so
    that fallback is a safety net rather than the normal case.
    """
    if lang != "hi":
        return english
    return HI.get(group, {}).get(key) or english


# --- The copy --------------------------------------------------------------
# Groups mirror the English sources exactly, so the completeness test can walk
# both and name anything missing.
HI: dict = {
    # presenters._VERDICTS -- the hero headline, the first line anyone reads.
    "verdict": {
        "Low": "साँस लेने के लिए आज अच्छा दिन है — बाहर घूम आइए।",
        "Moderate": "आज आपके लिए ठीक-ठाक है — बस ज़्यादा भागदौड़ मत कीजिए।",
        "High": "आज की हवा आपके फेफड़ों के लिए ठीक नहीं है — अंदर ही रहिए।",
        "Very High": "आज आपके फेफड़ों को घर के अंदर रहने की ज़रूरत है।",
        "Extreme": "बहुत ज़रूरी न हो तो बाहर मत निकलिए — यह हवा आपके लिए ख़तरनाक है।",
    },
    # risk.BAND_ADVICE -- the "what to do" line under the verdict.
    "band_advice": {
        "Low": "अपने काम आराम से कीजिए। कोई ख़ास सावधानी की ज़रूरत नहीं है।",
        "Moderate": "आप बाहर जा सकते हैं, लेकिन ज़ोर वाली कसरत थोड़ी देर की ही रखिए, और अगर "
                    "आप संवेदनशील समूह में हैं तो मास्क साथ रखिए।",
        "High": "बाहर कसरत मत कीजिए। बाहर जाना कम रखिए और बाहर N95 मास्क पहनिए।",
        "Very High": "हो सके तो घर के अंदर रहिए। कोई ज़रूरी काम हो तभी बाहर जाइए और तब N95 "
                     "मास्क पहनिए, और घर में एयर प्यूरीफ़ायर चलाइए।",
        "Extreme": "बाहर मत निकलिए। खिड़कियाँ बंद रखिए, प्यूरीफ़ायर चलाते रहिए, और तबीयत "
                   "ख़राब लगे तो डॉक्टर को दिखाइए।",
    },
    # risk._HEADLINE -- the drier API-contract headline.
    "headline": {
        "Low": "कम ख़तरा -- आज रोज़ के काम ठीक हैं",
        "Moderate": "मध्यम ख़तरा -- संवेदनशील लोग आराम से चलें",
        "High": "ज़्यादा ख़तरा -- आज बाहर मेहनत वाला काम न करें",
        "Very High": "बहुत ज़्यादा ख़तरा -- घर के अंदर रहें, बाहर मास्क पहनें",
        "Extreme": "अत्यधिक ख़तरा -- घर पर रहें, एयर प्यूरीफ़ायर चलाते रहें",
    },
    # normalize.AQI_MEANING -- what each CPCB band means for a person.
    "aqi_meaning": {
        "Good": "हवा साफ़ है। बाहर की गतिविधि सबके लिए ठीक है।",
        "Satisfactory": "लगभग सबके लिए ठीक है। कुछ बहुत संवेदनशील लोगों को ज़्यादा मेहनत "
                        "करते समय हल्की तकलीफ़ हो सकती है।",
        "Moderate": "ज़्यादातर लोगों के लिए ठीक है। संवेदनशील लोग (अस्थमा, दिल या फेफड़े की "
                    "बीमारी वाले, बच्चे, बुज़ुर्ग) ज़्यादा मेहनत वाले काम में आराम बरतें।",
        "Poor": "संवेदनशील लोगों के लिए हानिकारक। सभी लोग लंबी या तेज़ बाहरी गतिविधि कम करें; "
                "संवेदनशील लोग अंदर ही रहें।",
        "Very Poor": "सबके लिए हानिकारक। बाहर मेहनत वाला काम मत कीजिए; बाहर जाना ज़रूरी हो "
                     "तो N95 पहनिए और घर में प्यूरीफ़ायर चलाइए।",
        "Severe": "बेहद ख़तरनाक — यह स्वास्थ्य आपातकाल है। घर के अंदर रहिए, खिड़कियाँ बंद "
                  "कीजिए, प्यूरीफ़ायर चलाइए। सेहतमंद लोगों पर भी असर हो सकता है।",
        "Unknown": "अभी हवा की गुणवत्ता का आँकड़ा उपलब्ध नहीं है। जब तक पक्का पता न चले, "
                   "हवा को ख़राब मानकर ही चलिए।",
    },
    # normalize.AQI_BANDS labels -- Good, Satisfactory, ... Severe.
    "band_label": {
        "Good": "अच्छी",
        "Satisfactory": "संतोषजनक",
        "Moderate": "मध्यम",
        "Poor": "ख़राब",
        "Very Poor": "बहुत ख़राब",
        "Severe": "गंभीर",
        "Unknown": "पता नहीं",
    },
    # normalize.GLOSSARY -- the term definitions.
    "glossary": {
        "AQI": "Air Quality Index — हवा की गुणवत्ता का 0-500+ का स्कोर, जो कई प्रदूषकों को "
               "मिलाकर बनता है। नंबर जितना बड़ा, हवा उतनी ख़राब; भारत में CPCB का पैमाना "
               "चलता है (अच्छी से गंभीर तक)।",
        "PM2.5": "2.5 माइक्रोमीटर से छोटे बारीक कण — इतने छोटे कि फेफड़ों की गहराई और ख़ून "
                 "तक पहुँच जाते हैं। दिल्ली में सेहत की सबसे बड़ी चिंता यही है।",
        "PM10": "10 माइक्रोमीटर से छोटे मोटे धूल कण — साँस की नली और आँखों में जलन करते हैं; "
                "इनमें सड़क और निर्माण की धूल शामिल है।",
        "CPCB": "Central Pollution Control Board — भारत सरकार की वह संस्था जो पूरे देश में "
                "प्रदूषण की निगरानी करती है। किसी रीडिंग के साथ इसका नाम यह बताने के लिए "
                "आता है कि वह रीडिंग किस निगरानी नेटवर्क की है।",
        "µg/m³": "माइक्रोग्राम प्रति घन मीटर — यह बताने का तरीक़ा कि तय मात्रा की हवा में कोई "
                 "चीज़ कितनी घुली हुई है। एक माइक्रोग्राम ग्राम का दस लाखवाँ हिस्सा है, और "
                 "बड़ा नंबर मतलब उतनी ही हवा में उस चीज़ की ज़्यादा मात्रा।",
        "N95": "एक बार इस्तेमाल होने वाला, चेहरे पर कसकर बैठने वाला मास्क, जो अमेरिका के एक "
               "मानक पर परखी गई फ़िल्टर सामग्री से बनता है। इसी तरह के मास्क का यूरोपीय "
               "दर्जा FFP2 कहलाता है।",
        "Dominant pollutant": "वह प्रदूषक जो आज के AQI को सबसे ज़्यादा बढ़ा रहा है (जैसे "
                              "pm25 = बारीक कण, pm10 = धूल, o3 = ओज़ोन, no2 = गाड़ियों की गैस)।",
        "Risk score": "आज आपके लिए ख़तरे का 0-100 का अंदाज़ा, जो हवा की गुणवत्ता को आपकी "
                      "उम्र, बीमारी और आपकी योजना के साथ मिलाकर निकाला जाता है।",
    },
    # normalize.CONDITION_HELP -- what each health condition in the picker is.
    "condition_help": {
        "Fit": "ऐसी कोई बीमारी नहीं जिसकी वजह से प्रदूषित हवा आपके लिए एक आम बड़े व्यक्ति से "
               "ज़्यादा ख़तरनाक हो।",
        "Asthma": "अस्थमा — एक लंबी चलने वाली बीमारी जिसमें साँस की नलियाँ सिकुड़ जाती हैं और "
                  "उनमें सूजन आ जाती है। बारीक कण और गाड़ियों का धुआँ इसके आम कारण हैं।",
        "Heart condition": "दिल या ख़ून की नलियों की कोई भी बीमारी जिसका डॉक्टर ने पता लगाया "
                           "हो। बारीक कण थोड़े ही समय में सीने के दर्द और धड़कन की गड़बड़ी का "
                           "ख़तरा बढ़ा देते हैं।",
        "Pregnancy": "गर्भावस्था में बारीक कणों के प्रति संवेदनशीलता बढ़ जाती है, और ये कण "
                     "बच्चे के कम वज़न और समय से पहले जन्म से जुड़े हैं।",
        "COPD": "COPD (Chronic Obstructive Pulmonary Disease) — फेफड़ों को होने वाला लंबे "
                "समय का नुक़सान, जो अक्सर धूम्रपान या सालों तक धुएँ और धूल में रहने से होता "
                "है; इससे साँस की नलियाँ सँकरी हो जाती हैं और साँस लेना मुश्किल होता है। "
                "प्रदूषित हवा से यह अचानक बिगड़ सकती है।",
    },
    # UI chrome: nav, form labels, buttons, the disclaimer, the refusal.
    #
    # Key scheme: the exact strings the call sites ask for. Every key here is
    # the second argument of a ``T('ui', '<key>', '<english>')`` in
    # ``web/templates/*.html`` or of an ``i18n.t(lang, "ui", ...)`` in
    # ``web/main.py``. They are not derived from the English -- template chrome
    # has no source dict to key off -- so they are only correct by matching the
    # call site, and ``test_ui_and_guide_carry_the_keys_the_templates_request``
    # parses the templates rather than trusting a list written here.
    #
    # Several strings arrive as fragments, not as a sentence with a ``{field}``:
    # the template prints a time, a count or a place name between two separate
    # calls (``stale_before``/``stale_after``, ``prov_count_*``, ``no_trend_*``).
    # The Hindi is written so the pieces read as one natural sentence once the
    # template concatenates them, which sometimes means it is not a literal
    # split of the English fragments -- Hindi puts the noun before the
    # postposition where English puts the preposition before the noun.
    "ui": {
        # --- base.html: nav, theme, language, footer ---
        "skip": "मुख्य सामग्री पर जाएँ",
        "nav_label": "मुख्य",
        "nav_today": "आज",
        "nav_city": "शहर की नब्ज़",
        "nav_system": "सिस्टम",
        "nav_guide": "गाइड",
        "theme_group": "थीम",
        "theme_day": "दिन",
        "theme_night": "रात",
        "lang_group": "भाषा",
        "banner_label": "अनुवाद की स्थिति",
        "footer": "आपकी उम्र, बीमारी और आपकी योजना इसी सेशन में रहती है — कहीं दर्ज नहीं "
                  "की जाती। टेलीमेट्री में सिर्फ़ हैश किया हुआ सेशन आईडी और आपका चुना हुआ "
                  "इलाक़ा रहता है, ताकि System व्यू इलाक़े के हिसाब से रिक्वेस्ट दिखा सके।",
        "footer_sources": "डेटा: WAQI/CPCB · सलाह के स्रोत: CPCB, WHO, GINA, GOLD, AHA, "
                          "ACOG, EPA।",

        # --- city.html ---
        "tag_old": "पुरानी",
        "stations": "स्टेशन",
        # Follows the count and precedes the clock time, so it is phrased as a
        # label ("the time the page loaded") rather than as a verb.
        "page_loaded": "पेज लोड होने का समय",
        "median_aqi": "बीच का (median) AQI",
        "worst_first": "सबसे ख़राब पहले",
        "tag_legend": "CACHED का मतलब है कि उस जगह की रीडिंग हमारे पास है पर वह तीन घंटे से "
                      "पुरानी है, और टैग बताता है कि कितनी पुरानी। SAMPLE का मतलब है कि उस "
                      "जगह की कोई रीडिंग हमारे पास है ही नहीं, इसलिए वहाँ का एक आम आँकड़ा "
                      "दिखाया जा रहा है — उसे अभी की हवा नहीं, सिर्फ़ एक अंदाज़ा मानिए।",
        "sec_trend": "24 घंटे का रुझान",
        "last_24h": "पिछले 24 घंटे",
        "now": "अभी",
        "spark_caption": "दिल्ली का पैटर्न: रात भर प्रदूषण जमा होता है, दोपहर में कुछ राहत "
                         "मिलती है। किसी स्टेशन को चुनिए और उसका ग्राफ़ देखिए।",
        # The station name is printed between the first two fragments and the
        # command between the second and third, so the Hindi names the place
        # after the clause instead of before it.
        "no_trend_before": "अभी तक कोई रीडिंग सहेजी नहीं गई है —",
        "no_trend_after": "के लिए। पुराना डेटा भरने के लिए चलाइए",
        "no_trend_tail": "— या ऐप इस्तेमाल करते रहिए, हर लाइव रीडिंग आते ही अपने आप दर्ज हो "
                         "जाती है।",

        # --- today.html: hero ---
        "sec_now": "अभी की हवा",
        "your_risk": "आपका ख़तरा",
        # risk._BAND_TABLE labels, looked up as 'risk_band_' ~ label.
        "risk_band_Low": "कम",
        "risk_band_Moderate": "मध्यम",
        "risk_band_High": "ज़्यादा",
        "risk_band_Very High": "बहुत ज़्यादा",
        "risk_band_Extreme": "अत्यधिक",
        "baseline_chip": "सेहतमंद बड़ा व्यक्ति, वही योजना",
        "window_label": "अगर बाहर जाना ही पड़े",
        "window_note": "यह एक सामान्य पैटर्न है, हर घंटे का पूर्वानुमान नहीं",
        # The clock time is printed between the two. ``stale_after`` follows the
        # time with no separator in the template, so it carries its own leading
        # space.
        "stale_before": "लाइव फ़ीड बंद है — यह आसमान और यह सलाह पिछली अच्छी रीडिंग पर आधारित "
                        "है, जो",
        "stale_after": " की है, और फ़ीड लौटते ही अपने आप ताज़ा हो जाएगी।",

        # --- today.html: persona card ---
        "sec_persona": "आपका ब्यौरा",
        # The persona sentence follows, so this ends in a colon rather than
        # wrapping the name the way the English does.
        "advice_for": "यह सलाह इनके लिए है:",
        "btn_done": "हो गया",
        "btn_change": "जानकारी बदलें",
        "lbl_age": "उम्र",
        "lbl_condition": "स्वास्थ्य / बीमारी",
        "lbl_activity": "आप क्या करने वाले हैं",
        "lbl_locality": "आप कहाँ हैं",
        "btn_update": "सलाह अपडेट करें",
        "hint_session": "यह सिर्फ़ इसी सेशन में रहता है — कहीं दर्ज नहीं होता।",
        "link_score": "स्कोर कैसे निकाला जाता है, देखिए ›",
        "risk_notice": "इस स्कोर में मेहनत वाला हिस्सा प्रकाशित साँस लेने की दरों से आता है "
                       "(US EPA, जिसका भरोसा मध्यम आँका गया है)। बीमारी और उम्र वाला हिस्सा "
                       "हमारा अपना आकलन है, कोई जाँचा-परखा मेडिकल मॉडल नहीं।",

        # --- today.html: reading card ---
        "sec_reading": "रीडिंग",
        "cpcb_scale": "भारत का CPCB पैमाना, PM2.5 और PM10 से",
        "scale_low": "0 अच्छी",
        "scale_high": "गंभीर 500",
        "link_numbers": "इन नंबरों का मतलब क्या है? ›",

        # --- today.html: outlook ---
        "sec_outlook": "पाँच दिन का अनुमान",
        "outlook_title": "अगले पाँच दिन",
        "outlook_caption": "रोज़ का औसत, µg/m³, WAQI के पूर्वानुमान से बदला हुआ — यह मोटा "
                           "अनुमान है, हर घंटे का वादा नहीं।",

        # --- today.html: ask and answers ---
        "sec_ask": "SaafSaans से पूछिए",
        # The heading and the section's accessible name say the same thing; the
        # product name stays in Latin because that is how it is written.
        "ask_heading": "SaafSaans से पूछिए",
        "ask_sub": "ऊपर दी गई रीडिंग पर आधारित · आपकी अपनी स्थिति के लिए लिखा गया",
        "ask_placeholder": "बाहर जाने, मास्क, समय या लक्षणों के बारे में पूछिए…",
        "ask_label": "आपका सवाल",
        "btn_ask": "पूछें",
        "ask_hint": "पूछने के लिए Enter दबाइए। हर जवाब ऊपर दी गई जानकारी के हिसाब से लिखा "
                    "जाता है — किसी और के लिए सलाह चाहिए तो जानकारी बदल दीजिए।",
        "answered_for": "जवाब इनके लिए:",
        "refusal_title": "इस पर कार्रवाई नहीं की गई।",
        "refusal_body": "यह सहायक के काम करने का तरीक़ा बदलने की कोशिश जैसा लगा, इसलिए इसे "
                        "मॉडल तक पहुँचने से पहले ही रोक दिया गया। हवा, बचाव, मास्क, समय — "
                        "इन सब पर बेझिझक पूछिए।",
        "disclaimer": "यह सामान्य जानकारी है, डॉक्टरी सलाह नहीं।",
        # main.py, when an answer cannot be built. Carries a safe default
        # instruction, so it must not be shortened to an apology.
        "answer_error": "आपकी सलाह तैयार करने में कुछ गड़बड़ हो गई। शक हो तो बाहर कम से कम "
                        "निकलिए और बाहर N95 पहनिए।",

        # --- today.html: provenance panel ---
        "prov_label": "यह जवाब किस पर आधारित है",
        # The source count is printed between the two.
        "prov_count_before": "1 लाइव रीडिंग +",
        "prov_count_after": "गाइडेंस स्रोत",
        "prov_measured": "उस समय मापा गया",
        "prov_published": "इस्तेमाल की गई प्रकाशित गाइडेंस",
    },
    # The Guide's own prose. Keys are the strings guide.html asks for, in page
    # order: ``h_*`` headings, ``th_*`` table headers, ``q_*``/``a_*`` FAQ pairs
    # named after the question rather than numbered.
    "guide": {
        "sub": "इस साइट का हर नंबर और हर शब्द, आसान भाषा में।",
        "h_numbers": "नंबर",
        "h_conditions": "पिकर में दी गई बीमारियाँ",

        "h_bands": "CPCB की हवा-गुणवत्ता श्रेणियाँ",
        "bands_intro": "भारत का राष्ट्रीय पैमाना 0–500 तक चलता है। श्रेणी ही तय करती है कि ऊपर "
                       "आसमान का रंग क्या होगा और सलाह क्या कहेगी।",
        "th_band": "श्रेणी",
        "th_means": "आपके लिए इसका क्या मतलब है",

        "h_faq": "आम सवाल",
        "q_score_vs_aqi": "मेरा जोखिम स्कोर AQI से अलग क्यों है?",
        "a_score_vs_aqi": "AQI हवा के बारे में बताता है। जोखिम स्कोर उस हवा में आपके बारे में "
                          "बताता है — इसमें आपकी उम्र, बीमारी और आप क्या करने वाले हैं, यह भी "
                          "जुड़ जाता है। वही हवा घर के अंदर बैठे एक सेहतमंद बड़े व्यक्ति के लिए "
                          "मामूली हो सकती है और COPD वाले उस बुज़ुर्ग के लिए गंभीर, जो अभी बाहर "
                          "कसरत करने जा रहे हैं। इन दोनों नंबरों के बीच का फ़र्क़ ही इस साइट के "
                          "होने की पूरी वजह है।",
        "q_how_score": "जोखिम स्कोर कैसे निकाला जाता है?",
        "a_how_score": "नीचे इसका अपना पूरा हिस्सा है, जिसमें हर नंबर और वह नंबर कहाँ से आया, "
                       "दोनों लिखे हैं। छोटा जवाब: यह हवा से शुरू होता है, फिर जोड़ता है कि आप "
                       "कितनी ज़ोर से साँस लेंगे, और फिर यह कि यह हवा आपके शरीर पर कितनी "
                       "ज़्यादा भारी पड़ती है। यह फ़ैसला लेने में मदद करने वाला औज़ार है — कोई "
                       "जाँचा-परखा क्लिनिकल उपकरण नहीं, और न ही कोई निदान।",
        "q_data_source": "हवा का डेटा कहाँ से आता है?",
        "a_data_source": "भारत के CPCB नेटवर्क के ज़मीनी निगरानी स्टेशनों से, जिन्हें WAQI फ़ीड "
                         "के ज़रिए पढ़ा जाता है। जब वह फ़ीड नहीं चलती, साइट पिछली अच्छी रीडिंग "
                         "दिखाती है और उस पर साफ़-साफ़ CACHED लिखा होता है, और सलाह के ऊपर यह "
                         "बात कही भी जाती है। शहर की नब्ज़ पर CACHED टैग यह भी बताता है कि "
                         "रीडिंग कितनी पुरानी है, और जिस जगह की कोई रीडिंग हमारे पास है ही नहीं "
                         "उसे SAMPLE लिखा जाता है — यानी एक अंदाज़न आँकड़ा, कोई माप नहीं। पुरानी "
                         "या अंदाज़न चीज़ को कभी लाइव बनाकर नहीं दिखाया जाता।",
        "q_ignores": "जवाब कभी-कभी मेरे सवाल को अनदेखा क्यों कर देता है?",
        "a_ignores": "जवाब उसी व्यक्ति के लिए लिखे जाते हैं जो ‘आज’ वाले पेज पर दिखाया गया है, "
                     "किसी काल्पनिक व्यक्ति के लिए नहीं। ‘अगर मैं सेहतमंद होता तो?’ पूछने पर भी "
                     "सलाह उसी व्यक्ति के लिए आएगी जो आपने चुना है। व्यक्ति बदलिए और दोबारा "
                     "पूछिए — पूरा पेज, जवाब समेत, आपके चुने हुए व्यक्ति के लिए फिर से लिखा "
                     "जाता है।",
        "q_privacy": "मैं जो टाइप करता हूँ उसका क्या होता है?",
        "a_privacy": "आपकी उम्र, बीमारी और आपकी योजना पेज के पते और आपके सेशन में रहती है — ये "
                     "कभी किसी डेटाबेस में नहीं लिखी जातीं। आपका चुना हुआ इलाक़ा इसका एक अपवाद "
                     "है और उसे जानबूझकर रखा जाता है, ताकि System व्यू दिखा सके कि किन इलाक़ों "
                     "से रिक्वेस्ट आती हैं; उसे कभी आपकी बीमारी के साथ नहीं रखा जाता। सवालों की "
                     "जाँच होती है कि कहीं वे मॉडल को बरगलाने की कोशिश तो नहीं, उसके बाद ही वे "
                     "मॉडल तक जाते हैं। लॉग में एकतरफ़ा हैश किया हुआ सेशन आईडी और स्टेटस रहते "
                     "हैं; सुरक्षा लॉग में रोके गए सवाल का ज़्यादा से ज़्यादा 120 अक्षर का "
                     "टुकड़ा रखा जाता है।",
        "q_medical": "क्या यह डॉक्टरी सलाह है?",
        "a_medical": "नहीं। यह सार्वजनिक स्वास्थ्य स्रोतों (CPCB, WHO, GINA, GOLD, AHA, ACOG, "
                     "EPA) से बनी सामान्य जानकारी है। अगर आपकी तबीयत ठीक नहीं है, या आपकी रोज़ "
                     "की दवा पहले जैसा काम नहीं कर रही, तो डॉक्टर से संपर्क कीजिए।",

        "h_scale": "हवा का नंबर कहाँ से आता है, और वह क्या नहीं है",
        "scale_1": "रीडिंग भारत के CPCB निगरानी स्टेशनों से आती हैं, जो WAQI फ़ीड के ज़रिए "
                   "मिलती हैं। WAQI अपने नंबर अमेरिका के EPA सूचकांक पर छापता है, भारत के "
                   "नहीं — उसने जनवरी 2016 में हर भारतीय स्टेशन को अमेरिकी पैमाने पर कर दिया "
                   "था, और वह ख़ुद कहता है कि इसीलिए उसके आँकड़े भारत के अपने National AQI "
                   "पोर्टल से अलग होंगे।",
        "scale_2": "दोनों पैमानों में बड़ा फ़र्क़ है। 60 µg/m³ PM2.5 भारत के पैमाने पर 100 "
                   "यानी ‘संतोषजनक’ है, और अमेरिकी पैमाने पर क़रीब 154 यानी ‘Unhealthy’। "
                   "इसीलिए यह साइट बदलाव करती है: वह फ़ीड के अमेरिकी सूचकांक को वापस सांद्रता "
                   "में बदलती है, फिर उससे भारतीय आँकड़ा निकालती है। इस तरह यहाँ दिखने वाला "
                   "नंबर वैसा ही होता है जैसा दिल्ली में बाक़ी हर जगह दिखता है।",
        "scale_3": "वह नंबर क्या नहीं है। यह सिर्फ़ PM2.5 और PM10 से निकाला जाता है। भारत का "
                   "सरकारी तरीक़ा आठ तक प्रदूषकों का इस्तेमाल करता है और कम से कम तीन माँगता "
                   "है, इसलिए जिस दिन ओज़ोन जैसी कोई गैस हवा में सबसे ख़राब चीज़ हो, उस दिन "
                   "सरकारी आँकड़ा हमारे आँकड़े से ज़्यादा होगा। किसी भी जवाब के नीचे दिया गया "
                   "स्रोत पैनल हमारा नंबर और WAQI का असली नंबर, दोनों दिखाता है, ताकि आप "
                   "ख़ुद फ़र्क़ देख सकें।",

        "h_who": "विश्व स्वास्थ्य संगठन से तुलना",
        # The figure and its unit are printed in bold between these three, so
        # the Hindi names the guideline first and states the value after the
        # colon. ``who_1_after`` follows the bold run with no separator.
        "who_1_before": "PM2.5 के लिए संगठन की गाइडलाइन:",
        "who_1_unit": "µg/m³, 24 घंटे के औसत पर",
        "who_1_after": "। और साल भर के औसत पर 5 µg/m³। ‘आज’ वाले पेज की पंक्ति अभी की हवा की "
                       "तुलना 24 घंटे वाले आँकड़े से करती है, और यही बात उन्हीं शब्दों में कहती "
                       "भी है, क्योंकि दोनों एक चीज़ नहीं हैं: एक रीडिंग पूरे दिन का औसत नहीं "
                       "होती।",
        "who_2": "यह गाइडलाइन एक तरफ़ से जितनी सख़्त लगती है उससे ज़्यादा सख़्त है, और दूसरी "
                 "तरफ़ से ढीली। WHO 24 घंटे वाले स्तर को साल भर के रोज़ाना औसतों का 99वाँ "
                 "पर्सेंटाइल मानता है — यानी साल में तीन-चार दिन उससे ऊपर रहना भी गाइडलाइन के "
                 "अंदर ही है। यह किसी एक दिन की सीमा नहीं है। हम तुलना को एक ही अंक तक गोल कर "
                 "देते हैं और हमेशा ‘क़रीब’ कहते हैं, क्योंकि नीचे की रीडिंग इससे ज़्यादा "
                 "सटीकता के लायक़ नहीं है।",

        "h_risk": "आपका जोखिम स्कोर कैसे निकाला जाता है",
        "risk_intro": "यह स्कोर तीन चीज़ें जोड़ता है और 100 पर रुक जाता है: हवा कितनी ख़राब है "
                      "इसका एक शुरुआती आँकड़ा, आप जो करने वाले हैं उसमें कितनी हवा अंदर लेंगे, "
                      "और यह हवा एक आम बड़े व्यक्ति के मुक़ाबले आपके शरीर पर कितनी भारी पड़ती "
                      "है।",
        "h_risk_words": "स्कोर पर लिखे शब्दों का मतलब",
        "th_score": "स्कोर",
        "th_called": "इसे क्या कहते हैं",
        # Both precede their number in the template. Hindi puts "से कम" after a
        # number, so the first band is phrased as a ceiling instead.

        "h_researched": "वह हिस्सा जो प्रकाशित शोध से आता है",
        "researched_intro": "ज़्यादा ज़ोर से साँस लेने का मतलब है उसी हवा को ज़्यादा अंदर लेना। "
                            "कितना ज़्यादा, यह मापा जा चुका है, और हम अंदाज़ा लगाने के बजाय वही "
                            "माप इस्तेमाल करते हैं। नीचे के आँकड़े प्रति मिनट ली गई हवा के हैं "
                            "(घन मीटर प्रति मिनट में, वही इकाई जो स्रोत इस्तेमाल करता है), इस "
                            "साइट के तीनों उम्र-समूहों के लिए।",
        "th_age": "उम्र-समूह",
        "th_rest": "आराम में",
        "th_light": "हल्का",
        "th_moderate": "मध्यम",
        "th_hard": "ज़्यादा",
        "mapping_ours": "आपकी किस योजना को कितनी मेहनत माना जाए, यह हमारा अपना आकलन है, स्रोत "
                        "का नहीं:",

        "h_judgement": "वह हिस्सा जो हमारा अपना आकलन है",
        "judgement_body": "अस्थमा, COPD या दिल की बीमारी वाले व्यक्ति के लिए प्रदूषित हवा "
                          "कितनी ज़्यादा ख़राब है, इसका कोई एक प्रकाशित आँकड़ा नहीं है। कोई "
                          "ऐसा नंबर गढ़ने के बजाय जो आधिकारिक लगे, हम साफ़ कहते हैं कि नीचे "
                          "के आँकड़े सिर्फ़ हमारी यह समझ हैं कि किस पर सबसे ज़्यादा असर पड़ता "
                          "है — यह क्रम अच्छी तरह समर्थित है, इनके ठीक-ठीक आकार नहीं। यही "
                          "बात बच्चों और बुज़ुर्गों को दिए गए अतिरिक्त भार पर भी लागू होती "
                          "है, जिसकी वजहें असली हैं पर किसी नंबर में नहीं बँधतीं: बनते हुए "
                          "फेफड़े, शरीर के हर किलो पर ज़्यादा हवा, और कम बचाव।",
        "th_factor": "कारण",
        "th_points": "जुड़ने वाले अंक",
        "open_code": "अगर आपको लगता है कि यहाँ का संतुलन ग़लत है, तो आप हर आँकड़ा देख भी "
                     "सकते हैं और बदल भी सकते हैं — पूरा हिसाब सौ पंक्तियों के पढ़े जा सकने "
                     "वाले कोड में है, और उसमें आपसे कुछ भी छिपाया नहीं गया।",
    },
    # data.advisories -- the 34 seeded health advisories.
    #
    # Key rule, exact and deterministic, to be computed identically at lookup:
    #
    #     key = f"{a['source']}:{a['aqi_min']}-{a['aqi_max']}"
    #           f":{a['condition']}:{a['activity']}:{a['age_group']}"
    #
    # i.e. the five fields that identify a row, joined by ":" in that fixed
    # order, with the AQI band written "min-max" using the raw integers.
    # Example: "CPCB-AQI-scale:0-100:any:any:any".
    #
    # Source plus band alone is NOT enough and must not be used: two pairs of
    # seeded rows collide on it ("WHO-AQG-2021:201-300" and
    # "AHA-airpollution:201-300" each cover two different personas), and a
    # colliding key would silently serve one persona's Hindi to another. The
    # persona fields are therefore part of the key. A test walks ADVISORIES and
    # fails if any row has no entry here.
    "advisory": {
        "CPCB-AQI-scale:0-100:any:any:any":
            "AQI 100 तक (अच्छी/संतोषजनक): बाहर की गतिविधि सबके लिए ठीक है। 50 से ऊपर, "
            "ज़्यादा मेहनत वाले काम में कुछ संवेदनशील लोगों को हल्की तकलीफ़ हो सकती है।",
        "CPCB-AQI-scale:101-200:any:outdoor_exercise:any":
            "AQI 101-200 (मध्यम): सेहतमंद बड़े लोग बाहर कसरत कर सकते हैं, पर तेज़ कसरत का समय "
            "कम रखें। फेफड़े या दिल की बीमारी वाले लोग लंबी मेहनत कम करें।",
        "GINA-guidance:101-200:asthma:any:any":
            "AQI 101-200 और अस्थमा: अपना राहत वाला inhaler साथ रखें, कसरत घर के अंदर करें, और "
            "ज़्यादा ट्रैफ़िक वाली सड़कों से बचें जहाँ NO2 अचानक बढ़ जाती है।",
        "CPCB-AQI-scale:201-300:any:outdoor_exercise:any":
            "AQI 201-300 (ख़राब): बाहर कसरत मत करें। बाहर जाना ज़रूरी हो तो कम समय के लिए और "
            "बिना ज़ोर लगाए जाएँ, और अच्छी तरह फ़िट होने वाला N95/FFP2 मास्क पहनें।",
        "WHO-AQG-2021:201-300:any:commute:any":
            "AQI 201-300 में आना-जाना: गाड़ी के शीशे बंद रखें और हवा को recirculation पर रखें; "
            "दोपहिया पर N95 पहनें। मेट्रो में आमतौर पर सड़क के मुक़ाबले कम प्रदूषण लगता है।",
        "GINA-guidance:201-300:asthma:any:any":
            "AQI 201-300 और अस्थमा: खिड़कियाँ बंद करके घर के अंदर रहें, हो सके तो एयर "
            "प्यूरीफ़ायर चलाएँ, डॉक्टर के बताए अनुसार पहले से दवा लें, और अगर राहत वाले inhaler "
            "का इस्तेमाल बढ़ जाए तो डॉक्टर को दिखाएँ।",
        "AHA-airpollution:201-300:heart:any:any":
            "AQI 201-300 और दिल की बीमारी: बाहर मेहनत वाला काम न करें; बारीक कण थोड़े ही समय "
            "में सीने के दर्द (angina) और धड़कन की गड़बड़ी का ख़तरा बढ़ा देते हैं। सीने में "
            "जकड़न, धड़कन तेज़ होना या असामान्य रूप से साँस फूलने पर ध्यान दें।",
        "WHO-children-air:201-300:any:school_run:child":
            "AQI 201-300 और बच्चे: बच्चे तेज़ साँस लेते हैं, इसलिए उन पर असर ज़्यादा पड़ता है। "
            "बाहर खेलने का समय छोड़ दें, स्कूल आते-जाते बच्चों के नाप का N95 पहनाएँ, और "
            "क्लासरूम की खिड़कियाँ बंद रखें।",
        "CPCB-AQI-scale:301-400:any:any:any":
            "AQI 301-400 (बहुत ख़राब): सबको बाहर बिताया जाने वाला समय कम से कम करना चाहिए। "
            "ज़्यादा देर रहने पर साँस की बीमारी होने की आशंका है। बाहर N95 ज़रूरी है; घर के "
            "अंदर प्यूरीफ़ायर तेज़ पर चलाएँ।",
        "ACSM-guidance:301-400:any:outdoor_exercise:any":
            "AQI 301-400: बाहर की कसरत पूरी तरह रद्द कर दें। कसरत करने से अंदर जाने वाली "
            "प्रदूषित हवा 5-10 गुना बढ़ जाती है। कसरत घर के अंदर करें; दिल्ली की सर्दी में "
            "सुबह-सुबह की हवा ज़्यादा साफ़ नहीं होती।",
        "ACOG-airquality:301-400:pregnancy:any:any":
            "AQI 301-400 और गर्भावस्था: PM2.5 का असर बच्चे के कम वज़न और समय से पहले जन्म से "
            "जुड़ा है। फ़िल्टर की हुई हवा में घर के अंदर रहें, ज़रूरी काम से बाहर जाना ही पड़े "
            "तो N95 पहनें, और कोई तकलीफ़ बनी रहे तो अपनी डॉक्टर से बात करें।",
        "GOLD-guidance:301-400:copd:any:any":
            "AQI 301-400 और COPD: बीमारी बिगड़ने का ख़तरा बहुत ज़्यादा है। साफ़ की हुई हवा में "
            "घर के अंदर रहें, आपातकालीन दवा पास रखें, ऑक्सीमीटर हो तो SpO2 देखते रहें, और आराम "
            "करते हुए भी साँस फूलने लगे तो तुरंत डॉक्टर के पास जाएँ।",
        "CPCB-AQI-scale:401-999:any:any:any":
            "AQI 400 से ऊपर (गंभीर): यह स्वास्थ्य आपातकाल जैसी हालत है। बाहर की हवा से पूरी "
            "तरह बचें। खिड़कियाँ बंद करें, प्यूरीफ़ायर चलाएँ; सेहतमंद लोगों पर भी असर हो सकता "
            "है। GRAP-IV की पाबंदियाँ मानें।",
        "WHO-AQG-2021:401-999:any:any:senior":
            "AQI 400 से ऊपर और बुज़ुर्ग: दिल और साँस की दिक़्क़तों का सबसे ज़्यादा ख़तरा इसी "
            "उम्र में होता है। बाहर बिल्कुल न निकलें; ज़रूरत का सामान घर मँगवाएँ; उलझन, सीने "
            "में दर्द या साँस लेने में तकलीफ़ दिखे तो उसे आपात स्थिति मानें।",
        "EPA-indoor-air:151-999:any:stay_home:any":
            "ख़राब हवा वाले दिनों में घर पर रहना: खिड़कियाँ बंद रखें, जिस कमरे में सबसे ज़्यादा "
            "रहते हैं वहाँ HEPA प्यूरीफ़ायर चलाएँ, घर के अंदर धुआँ करने वाली चीज़ों (अगरबत्ती, "
            "तलना) से बचें, और AQI गिरे तभी थोड़ी देर के लिए हवा आने दें।",
        "GINA-guidance:51-150:asthma:any:any":
            "AQI 51-150 और अस्थमा: आमतौर पर सह लिया जाता है, पर PM2.5 से तकलीफ़ फिर भी शुरू हो "
            "सकती है। राहत वाला inhaler पास रखें, भीड़-भाड़ वाले ट्रैफ़िक के रास्तों से बचें "
            "जहाँ NO2 ज़्यादा है, और सीने में जकड़न या घरघराहट लगे तो अंदर आ जाएँ।",
        "AHA-airpollution:51-150:heart:outdoor_exercise:any":
            "AQI 51-150 और दिल की बीमारी: बाहर हल्की से मध्यम कसरत आमतौर पर ठीक है, पर PM2.5 "
            "ऊपरी आधे हिस्से में हो तो ज़ोर कम कर दें। सीने में तकलीफ़, धड़कन तेज़ होना या "
            "असामान्य रूप से साँस फूलने पर रुककर आराम करें।",
        "GOLD-guidance:51-150:copd:any:any":
            "AQI 51-150 और COPD: बाहर का काम धीरे-धीरे करें और भारी ट्रैफ़िक के पास लंबी मेहनत "
            "से बचें, वहाँ NO2 और PM10 सबसे ज़्यादा होते हैं। आपातकालीन दवा साथ रखें और खाँसी "
            "या बलगम बढ़े तो उस पर ध्यान दें।",
        "ACOG-airquality:51-150:pregnancy:any:any":
            "AQI 51-150 और गर्भावस्था: रोज़ का बाहर का काम ठीक है, पर व्यस्त सड़कों के किनारे "
            "ज़्यादा देर न रुकें। थोड़ा-थोड़ा PM2.5 भी पूरी गर्भावस्था में जुड़ता जाता है, "
            "इसलिए हो सके तो पार्क और शांत गलियाँ चुनें।",
        "WHO-children-air:51-150:any:school_run:child":
            "AQI 51-150 में बच्चों का स्कूल आना-जाना: आमतौर पर ठीक है, पर खड़ी चालू गाड़ियों "
            "वाली मुख्य सड़कों से हटकर गलियों से जाएँ जहाँ NO2 कम होता है। जिन बच्चों को "
            "घरघराहट होती है उन्हें आराम से चलने को कहें।",
        "WHO-AQG-2021:51-150:any:outdoor_exercise:senior":
            "AQI 51-150 में बुज़ुर्गों की बाहर कसरत: कसरत मध्यम रखें और पानी पीते रहें। धूप "
            "वाली गरम दोपहर में अक्सर ओज़ोन सबसे ज़्यादा होता है, इसलिए सुबह या शाम की सैर से "
            "O3 का असर कम रहेगा।",
        "AHA-airpollution:101-200:heart:commute:any":
            "AQI 101-200 में दिल की बीमारी के साथ आना-जाना: दोपहिया के बजाय मेट्रो या "
            "recirculation पर चल रही बंद गाड़ी चुनें, क्योंकि सड़क किनारे PM2.5 और NO2 सबसे "
            "ज़्यादा होते हैं। जल्दबाज़ी न करें; प्रदूषित हवा में अचानक ज़ोर लगाना दिल पर भारी "
            "पड़ सकता है।",
        "GOLD-guidance:101-200:copd:any:any":
            "AQI 101-200 और COPD: बाहर कम समय बिताएँ और मेहनत वाले काम से बचें। ज़रूरी काम के "
            "लिए N95 पहनने पर विचार करें, PM10 से बचने के लिए खिड़कियाँ बंद रखें, और साँस फूलना "
            "या राहत वाले inhaler का इस्तेमाल बढ़ते ही तुरंत क़दम उठाएँ।",
        "ACOG-airquality:101-200:pregnancy:commute:any":
            "AQI 101-200 में गर्भावस्था के दौरान आना-जाना: PM2.5 कम अंदर जाए, इसके लिए मेट्रो "
            "या recirculation पर चल रही बंद गाड़ी चुनें। दोपहिया पर हों या सड़क किनारे इंतज़ार "
            "कर रही हों तो अच्छी तरह फ़िट होने वाला N95 पहनें।",
        "WHO-children-air:101-200:any:school_run:child":
            "AQI 101-200 में बच्चों का स्कूल आना-जाना: तेज़ चलें पर रास्ता छोटा रखें, मुख्य "
            "सड़क वाले बस स्टॉप से बचें जहाँ NO2 और PM10 जमा होते हैं, और जो बच्चे जल्दी थकते "
            "हैं या जिन्हें घरघराहट होती है उनके लिए N95 साथ रखें। स्कूल से कहें कि खेल की "
            "कक्षा (PE) घर के अंदर कराएँ।",
        "AIIMS-advisory:101-200:any:any:senior":
            "AQI 101-200 और बुज़ुर्ग: बाहर ज़्यादा देर रहना कम करें और बाहर के भारी काम न करें। "
            "बारीक कण ब्लड प्रेशर और दिल की धड़कन पर असर डालते हैं; ज़रूरी दवाइयाँ घर में रखें "
            "और शाम को, जब PM2.5 बढ़ता है, खिड़कियाँ बंद रखें।",
        "GOLD-guidance:201-300:copd:any:any":
            "AQI 201-300 और COPD: प्यूरीफ़ायर चलाकर घर के अंदर रहें और किसी तरह की मेहनत न "
            "करें। ज़्यादा PM10 और PM2.5 से बीमारी बिगड़ने का ख़तरा तेज़ी से बढ़ता है, इसलिए "
            "आपातकालीन दवा पास रखें और आराम करते हुए साँस फूलने लगे तो देर किए बिना डॉक्टर को "
            "दिखाएँ।",
        "ACOG-airquality:201-300:pregnancy:any:any":
            "AQI 201-300 और गर्भावस्था: बाहर निकलना कम से कम करें और घर के अंदर हवा फ़िल्टर "
            "करें। इस स्तर पर लगातार PM2.5 का असर बच्चे की बढ़त कम होने से जुड़ा है; ज़रूरी काम "
            "से बाहर जाना ही पड़े तो N95 पहनें और कोई तकलीफ़ बनी रहे तो अपनी डॉक्टर को बताएँ।",
        "AHA-airpollution:201-300:heart:commute:any":
            "AQI 201-300 में दिल की बीमारी के साथ आना-जाना: दोपहिया और खुले ऑटो से बचें, वहाँ "
            "PM2.5 बहुत बढ़ जाता है; recirculation पर चल रही बंद गाड़ी या मेट्रो लें, और N95 "
            "पहने रहें। सीने में दर्द या धड़कन तेज़ होने को आपात स्थिति मानें।",
        "WHO-AQG-2021:201-300:any:commute:senior":
            "AQI 201-300 में बुज़ुर्गों का आना-जाना: ग़ैर-ज़रूरी यात्रा टाल दें। जाना ही पड़े "
            "तो मेट्रो या recirculation पर चल रही बंद गाड़ी लें, N95 पहनें, और सड़क किनारे "
            "स्टॉप पर खड़े होने से बचें जहाँ PM2.5 और NO2 सबसे ख़राब होते हैं।",
        "EPA-indoor-air:201-300:any:stay_home:any":
            "AQI 201-300 में घर पर रहना: खिड़कियाँ बंद करें, जिन कमरों में लोग हैं वहाँ HEPA "
            "प्यूरीफ़ायर लगातार चलाएँ, और अगरबत्ती, तलने तथा पोंछा लगाते समय उड़ने वाली धूल से "
            "बचें, क्योंकि इनसे घर के अंदर PM2.5 और बढ़ता है। बाहर का AQI तेज़ी से गिरे तभी हवा "
            "आने दें।",
        "Lancet-Planetary-Health:101-300:asthma:outdoor_exercise:any":
            "AQI 101-300 में अस्थमा के साथ बाहर कसरत: ज़ोर लगाने से अंदर जाने वाला PM2.5 और "
            "ओज़ोन कई गुना बढ़ जाता है। कसरत घर के अंदर करें, या बाहर ही करनी हो तो सुबह, O3 "
            "बढ़ने से पहले, कम ट्रैफ़िक वाली हरी जगह चुनें और डॉक्टर के बताए अनुसार पहले से दवा "
            "लें।",
        "WHO-children-air:151-400:any:outdoor_exercise:child":
            "AQI 151-400 में बच्चों का बाहर खेलना या खेलकूद: रद्द कर दें। बच्चे तेज़ साँस लेते "
            "हैं और उनके फेफड़े अभी बन रहे होते हैं, इसलिए PM2.5 और NO2 उन्हें ज़्यादा नुक़सान "
            "पहुँचाते हैं; खेल घर के अंदर कराएँ और स्कूल से कहें कि बाहर की खेल-कक्षा (PE) बंद "
            "रखें।",
        "AHA-airpollution:301-999:heart:any:senior":
            "AQI 300 से ऊपर, दिल की बीमारी वाले बुज़ुर्ग: दिल का दौरा और धड़कन की गड़बड़ी का "
            "सबसे ज़्यादा ख़तरा। बाहर बिल्कुल न निकलें, घर के अंदर हवा साफ़ रखें, डॉक्टर की "
            "बताई दवाइयाँ (जैसे nitrate) पास रखें, और सीने में दर्द या साँस फूलने को आपात "
            "स्थिति मानें।",
    },
}
