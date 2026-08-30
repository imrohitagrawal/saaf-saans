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

What stays in English on a Hindi page, and why
----------------------------------------------
Three kinds of Latin text remain, and all three are deliberate:

* **Technical terms a Delhi reader says out loud in English** -- AQI, PM2.5,
  PM10, N95, FFP2, COPD, CPCB, WHO, WAQI, HEPA, SpO2, NO2, O3. Transliterating
  them makes them harder to recognise, not easier.
* **Citations.** The WHO guideline reference and the EPA Exposure Factors
  Handbook reference on the Guide are identifiers of published documents, not
  copy; they are printed by ``guide.html`` and ``risk.SOURCE_EPA``, not from
  this file, and translating them would make them harder to look up.
* **The initials of the bodies the advice comes from** -- GINA, GOLD, AHA,
  ACOG, EPA -- in the footer and in the Guide's "is this medical advice?"
  answer. These are how the organisations are named in India, in Hindi as well
  as in English.

Everything a reader is told to *do* is Hindi. Localities are never translated:
they are proper nouns, and the picker's values are what people say out loud.

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


def place(lang: str, name: str) -> str:
    """A locality or region name for display. Falls back to the English.

    Separate from ``t`` because the caller almost always needs the untranslated
    string too -- it is the form value, the query parameter and the key into
    ``waqi.FEED_MAP``. Translating the label while keeping the value is the
    whole point; translating both would break the picker.
    """
    return t(lang, "locality", name, name)


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


# Clock times, written the way each language writes them.
#
# English suffixes the meridiem; Hindi names the part of the day before the
# number and closes with a single "बजे", which is what the four hand-written
# window strings this replaces already did. The daypart boundaries are taken
# from those four strings, not invented: they wrote 11 AM as सुबह, 12 and 3 PM
# as दोपहर, 4 PM as शाम and 11 PM as रात.
#
# The words are literals here rather than corpus keys because the AST scanner
# in test_i18n only sees `i18n.t(group, key)` call sites; keys reached from
# inside this module would read as orphans and fail the corpus test.
_HI_DAYPARTS = ((4, 11, "सुबह"), (12, 15, "दोपहर"), (16, 19, "शाम"))
_HI_NIGHT = "रात"


def _hi_daypart(hour: int) -> str:
    hour %= 24
    for low, high, word in _HI_DAYPARTS:
        if low <= hour <= high:
            return word
    return _HI_NIGHT


def _hour12(hour: int) -> int:
    return (hour % 12) or 12


def clock_range(lang: str, start: int, end: int) -> str:
    """A half-open hour range as a reader of ``lang`` would say it.

    ``end`` is exclusive and may be 24, which English calls midnight and Hindi
    writes as the 12 of रात. English prints the meridiem once when both ends
    share it. Hindi repeats the daypart only when the range crosses one, so
    "सुबह 9 से दोपहर 12 बजे" but "सुबह 6 से 9 बजे".
    """
    if lang != "hi":
        if end == 24:
            return f"{_hour12(start)} {'AM' if start < 12 else 'PM'}-midnight"
        start_mer = "AM" if start < 12 else "PM"
        end_mer = "AM" if end < 12 else "PM"
        if start_mer == end_mer:
            return f"{_hour12(start)}-{_hour12(end)} {end_mer}"
        return f"{_hour12(start)} {start_mer}-{_hour12(end)} {end_mer}"
    first, second = _hi_daypart(start), _hi_daypart(end)
    if first == second:
        return f"{first} {_hour12(start)} से {_hour12(end)} बजे"
    return f"{first} {_hour12(start)} से {second} {_hour12(end)} बजे"


# --- The copy --------------------------------------------------------------
# Groups mirror the English sources exactly, so the completeness test can walk
# both and name anything missing.
HI: dict = {
    # presenters._VERDICTS -- the hero headline, the first line anyone reads.
    "verdict": {
        "Low": "साँस लेने के लिए आज अच्छा दिन है — बाहर घूम आइए।",
        "Moderate": "आज आपके लिए ठीक-ठाक है — बस ज़्यादा भागदौड़ मत कीजिए।",
        "High": "आज की हवा आपके फेफड़ों के लिए ठीक नहीं है — अंदर ही रहिए।",
        "Very High": "आज की हवा आपके फेफड़ों पर भारी पड़ेगी — घर के अंदर ही रहिए।",
        "Extreme": "बहुत ज़रूरी न हो तो बाहर मत निकलिए — यह हवा आपके लिए ख़तरनाक है।",
    },
    # presenters.no_reading_verdict -- the hero headline when there is no
    # reading at all. Its own group, not a sixth entry in "verdict": the five
    # verdicts are keyed by risk band and each asserts something about the air,
    # and this one exists precisely because no band and no assertion apply.
    "hero": {
        "no_reading": "{place} की हवा की कोई रीडिंग अभी हमारे पास नहीं है।",
        # Deliberately not the line above. A held reading IS a reading -- its
        # number is printed further down the same page -- so saying we have
        # none would make the page disagree with itself.
        "held": "{place} के लिए हम एक पुरानी रीडिंग सहेजे हुए हैं।",
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
        "AQI": "हवा की गुणवत्ता का सूचकांक — 0-500+ का स्कोर, जो कई प्रदूषकों को "
               "मिलाकर बनता है। नंबर जितना बड़ा, हवा उतनी ख़राब; भारत में CPCB का पैमाना "
               "चलता है (अच्छी से गंभीर तक)।",
        "PM2.5": "2.5 माइक्रोमीटर से छोटे बारीक कण — इतने छोटे कि फेफड़ों की गहराई और ख़ून "
                 "तक पहुँच जाते हैं। दिल्ली में सेहत की सबसे बड़ी चिंता यही है।",
        "PM10": "10 माइक्रोमीटर से छोटे मोटे धूल कण — साँस की नली और आँखों में जलन करते हैं; "
                "इनमें सड़क और निर्माण की धूल शामिल है।",
        "CPCB": "केंद्रीय प्रदूषण नियंत्रण बोर्ड — भारत सरकार की वह संस्था जो पूरे देश में "
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
                      "उम्र, बीमारी और आप जो करने वाले हैं, उसे मिलाकर निकाला जाता है।",
        # Mirrors normalize.GLOSSARY's eleven source-tag entries. The acronym
        # each keeps in Latin is already on the ALLOWED list in
        # test_hindi_completeness.py -- the full institution name is
        # translated, exactly as the CPCB entry above never spells out
        # "Central Pollution Control Board" in English.
        "CPCB-AQI-scale": "केंद्रीय प्रदूषण नियंत्रण बोर्ड — ऊपर वाली वही भारत सरकार की संस्था। "
                          "इस टैग का मतलब है कि सलाह किसी नामी चिकित्सा संस्था की नहीं, बल्कि "
                          "बोर्ड के अपने प्रकाशित AQI पैमाने से ली गई है।",
        "GINA-guidance": "अस्थमा की वैश्विक पहल (GINA) — अस्थमा की देखभाल पर दिशा-निर्देश जारी "
                         "करने वाली एक अंतरराष्ट्रीय संस्था। इस टैग की सलाह उसी की है।",
        "GOLD-guidance": "दीर्घकालिक अवरोधी फेफड़े की बीमारी की वैश्विक पहल (GOLD) — COPD की "
                         "देखभाल पर दिशा-निर्देश जारी करने वाली एक अंतरराष्ट्रीय संस्था। इस "
                         "टैग की सलाह उसी की है।",
        "ACSM-guidance": "अमेरिकी खेल चिकित्सा महाविद्यालय (ACSM) — व्यायाम विज्ञान से जुड़ी एक "
                         "पेशेवर संस्था। इस टैग की सलाह उसी की है, प्रदूषित हवा में कसरत करने "
                         "को लेकर।",
        "AHA-airpollution": "अमेरिकी हृदय संघ (AHA) — दिल की सेहत से जुड़ी एक पेशेवर संस्था। इस "
                            "टैग की सलाह उसी की है, वायु प्रदूषण और दिल पर उसके असर को लेकर।",
        "WHO-AQG-2021": "विश्व स्वास्थ्य संगठन (WHO) के 2021 वायु गुणवत्ता दिशा-निर्देश — "
                        "सुरक्षित प्रदूषक स्तर पर उसकी सबसे हालिया वैश्विक सिफ़ारिशें।",
        "WHO-children-air": "बच्चों और वायु प्रदूषण पर विश्व स्वास्थ्य संगठन (WHO) के "
                            "दिशा-निर्देश — बच्चे अपने आकार के हिसाब से तेज़ साँस लेते हैं और "
                            "ज़्यादा असर में आते हैं, इसलिए यह सलाह ख़ास उन्हीं के लिए लिखी गई है।",
        "ACOG-airquality": "अमेरिकी प्रसूति एवं स्त्री रोग महाविद्यालय (ACOG) — गर्भावस्था की "
                           "देखभाल से जुड़ी एक पेशेवर संस्था। इस टैग की सलाह उसी की है, वायु "
                           "गुणवत्ता और गर्भावस्था को लेकर।",
        "AIIMS-advisory": "अखिल भारतीय आयुर्विज्ञान संस्थान (AIIMS) — दिल्ली में सरकार द्वारा "
                          "संचालित एक चिकित्सा संस्थान और अस्पताल। इस टैग की सलाह उसी की है।",
        "EPA-indoor-air": "अमेरिकी पर्यावरण संरक्षण एजेंसी (EPA) के घर के अंदर की हवा पर "
                          "दिशा-निर्देश — यहाँ ख़राब हवा वाले दिन घर पर रहने के लिए इस्तेमाल "
                          "किए गए हैं, बाहर की रीडिंग के लिए नहीं।",
        "Lancet-Planetary-Health": "लैंसेट प्लैनेटरी हेल्थ (Lancet) — एक समीक्षित चिकित्सा "
                                   "पत्रिका। इस टैग की सलाह उसमें छपे शोध पर आधारित है।",
    },
    # normalize.CONDITION_HELP -- what each health condition in the picker is.
    "condition_help": {
        "Fit": "ऐसी कोई बीमारी नहीं जिसकी वजह से प्रदूषित हवा आपके लिए एक आम बड़े व्यक्ति से "
               "ज़्यादा ख़तरनाक हो।",
        # No leading term name. The template composes "{label} — {help}", so a
        # value that opens with its own name renders it twice ("अस्थमा — अस्थमा
        # — ..."). The English values never did this; two of the Hindi ones did,
        # and it was visible only on the rendered Hindi page.
        "Asthma": "एक लंबी चलने वाली बीमारी जिसमें साँस की नलियाँ सिकुड़ जाती हैं और "
                  "उनमें सूजन आ जाती है। बारीक कण और गाड़ियों से निकलने वाली गैसें इसे भड़काने वाली आम चीज़ें हैं।",
        "Heart condition": "दिल या ख़ून की नलियों की कोई भी बीमारी जिसका डॉक्टर ने पता लगाया "
                           "हो। बारीक कण थोड़े ही समय में सीने के दर्द और धड़कन की गड़बड़ी का "
                           "ख़तरा बढ़ा देते हैं।",
        "Pregnancy": "गर्भावस्था में बारीक कणों के प्रति संवेदनशीलता बढ़ जाती है, और ये कण "
                     "बच्चे के कम वज़न और समय से पहले जन्म से जुड़े हैं।",
        "COPD": "फेफड़ों को होने वाला लंबे "
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
    # call site, and ``test_the_corpus_carries_every_key_the_code_requests``
    # parses the templates rather than trusting a list written here.
    #
    # Several strings arrive as fragments, not as a sentence with a ``{field}``:
    # the template prints a time, a count or a place name between two separate
    # calls (``prov_count_*``, ``no_trend_*``).
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
        "footer": "आपकी उम्र, बीमारी और आपके काम इसी सेशन में रहते हैं — कहीं दर्ज नहीं "
                  "की जाती। टेलीमेट्री में सिर्फ़ हैश किया हुआ सेशन आईडी और आपका चुना हुआ "
                  "इलाक़ा रहता है, ताकि सिस्टम व्यू इलाक़े के हिसाब से रिक्वेस्ट दिखा सके। "
                  "आपका ब्राउज़र जो चौड़ाई बताता है, उसकी श्रेणी भी गिनी जाती है — उसके "
                  "साथ और कुछ नहीं जोड़ा जाता।",
        # Printed around <span lang="en">data.gov.in</span>. Primary source
        # first, because that is the order the code reads them in.
        "footer_sources_before": "डेटा: CPCB, स्रोत",
        "footer_sources_after": " · जब वहाँ कुछ न मिले तो WAQI",
        "footer_sources_waqi_only": "डेटा: WAQI फ़ीड",
        "footer_sources_none": "डेटा: इस तैनाती पर कोई लाइव स्रोत सेट नहीं है, इसलिए यहाँ "
                               "कोई भी रीडिंग लाइव नहीं है",
        "footer_advisories": "· सलाह के स्रोत: CPCB, WHO, GINA, GOLD, AHA, ACOG, EPA।",

        # --- city.html ---
        # ``tag_cached`` is printed immediately before ``tag_old``, so the two
        # cannot both be "पुरानी" or the chip reads "पुरानी · 5 घंटे पुरानी".
        "tag_cached": "सहेजी हुई",
        # Replaces "नमूना" (sample). The page no longer holds a stand-in figure
        # to call a sample -- it holds nothing, and says so.
        "tag_no_reading": "कोई रीडिंग नहीं",
        "tag_old": "पुरानी",
        "region_delhi": "दिल्ली",
        "region_ncr": "एनसीआर",
        # Station-age units, printed after a Latin digit ("5 घंटे").
        "age_unit_min": "मिनट",
        "age_unit_hours": "घंटे",
        "age_unit_days": "दिन",
        # Names the two chips by the words they now carry in Hindi, not by
        # their English originals -- a legend that names a tag the page does
        # not print is a legend for a different page.
        # The grid sorts worst-first, so it invites comparison between tiles.
        # A figure from one particulate is not comparable with one from two.
        # Named in plain language: the particulate belongs on the Today page.
        "tag_partial": "अधूरी",
        "tag_partial_legend": "‘अधूरी’ का मतलब है कि उस स्टेशन ने नंबर में जाने वाली चीज़ों में "
                              "से सिर्फ़ कुछ ही मापी हैं, इसलिए उसका आँकड़ा बाक़ी स्टेशनों से "
                              "सीधे तुलना करने लायक़ नहीं है। उस स्टेशन को खोलकर देखिए कि "
                              "उसने क्या मापा है।",
        "tag_legend": "‘सहेजी हुई’ का मतलब है कि उस जगह की जो रीडिंग हमारे पास पहले से है "
                      "हम वही दिखा रहे हैं — अभी-अभी आई हुई नहीं — और टैग बताता है कि माप "
                      "कितना पुराना है। ‘कोई रीडिंग नहीं’ का मतलब "
                      "है कि उस जगह का कोई आँकड़ा हमारे पास है ही नहीं — इसलिए वहाँ कोई नंबर "
                      "नहीं दिखाया जाता, क्योंकि हमारे पास है नहीं और हम बनाएँगे नहीं।",
        # Per-row `title` definitions: the legend above, shortened to one
        # sentence each, because the row is where the tag is read.
        "tag_cached_def": "पहले की रीडिंग जो अब भी हमारे पास सहेजी हुई है, अपनी उम्र के "
                          "साथ — यह अभी की हवा नहीं है।",
        "tag_no_reading_def": "इस स्टेशन का कोई आँकड़ा हमारे पास नहीं है, इसलिए कोई नंबर "
                              "नहीं दिखाया गया — हम बनाते भी नहीं।",
        "tag_partial_def": "नंबर में जाने वाली चीज़ों में से सिर्फ़ कुछ से निकाला गया है, "
                           "इसलिए बाक़ी स्टेशनों से इसकी सीधी तुलना नहीं हो सकती।",
        "sec_trend": "24 घंटे का रुझान",
        "last_24h": "पिछले 24 घंटे",
        "now": "अभी",
        "spark_caption": "दिल्ली का पैटर्न: रात भर प्रदूषण जमा होता है, दोपहर में कुछ राहत "
                         "मिलती है। किसी स्टेशन को चुनिए और उसका ग्राफ़ देखिए।",
        # The station name is printed between the two fragments, so the Hindi
        # names the place after the clause instead of before it. There used to
        # be a third fragment with a backfill command between the second and
        # third; the command is gone, because running it wrote invented AQI
        # into the index this very curve is drawn from.
        "no_trend_before": "अभी तक कोई रीडिंग सहेजी नहीं गई है —",
        "no_trend_tail": "के लिए। हर लाइव रीडिंग आते ही अपने आप दर्ज हो जाती है, इसलिए "
                         "फ़ीड जवाब देते ही यह भरता जाएगा।",
        # Reconciles the header's figure with the empty chart under it.
        "no_trend_number_note": "ऊपर हेडर का आँकड़ा वह सबसे ताज़ा अकेली रीडिंग है जो हम "
                                "दिखा सकते हैं; यह ग्राफ़ सिर्फ़ सहेजी हुई रीडिंगों से बनता "
                                "है, इसलिए जब तक वह इतिहास न बन जाए, ऊपर नंबर होते हुए "
                                "भी ग्राफ़ ख़ाली रह सकता है।",

        # --- today.html: hero ---
        "sec_now": "आज की हवा",
        "your_risk": "आपका ख़तरा",
        # First visit, before any persona is applied: the kicker and the risk
        # chip both label the default persona as an example rather than
        # claiming "आपका". Devanagari has no case, so the kicker's CSS
        # uppercasing changes nothing here.
        "example_prefix": "उदाहरण —",
        "example_risk": "उदाहरण व्यक्ति",
        # Replaces the score chip when there is no reading. The score is built
        # on the air, and an assumed AQI would make the number an invented one.
        "risk_no_reading": "कोई रीडिंग नहीं — आपका ख़तरा नहीं आँका जा सकता",
        "risk_held": "सहेजी हुई रीडिंग — आपका ख़तरा नहीं आँका जा सकता",
        # Replaces the CATEGORY meaning when the only reading we hold is an
        # older one. Hindi already had a safe aqi_meaning["Unknown"] and so was
        # never exposed to the defect this string fixes -- it is added so both
        # languages say the same thing for the same reason, rather than one
        # being correct by the accident of having a translation at all.
        "meaning_held": "यह हवा का वह हाल है जब यहाँ आख़िरी बार माप हुई थी, अभी का "
                        "नहीं। यह कितनी सुरक्षित है, इसके बारे में इससे कुछ भी नहीं "
                        "निकाला गया है।",
        # Wraps the last stored reading and its date. Two fragments because the
        # template interleaves the number and the date between them, and Hindi
        # puts the date before the verb: "<date> को यहाँ आख़िरी बार AQI <n> दर्ज
        # हुआ था" would need a different assembly order, so the English order is
        # kept and the Hindi reads naturally within it.
        "last_reported_before": "यहाँ आख़िरी बार हमने",
        "last_reported_here": "दर्ज किया था —",
        # Replaces the band advice when there is no band, because there is no
        # reading. The one instruction that does not need to know the air.
        "advice_no_reading": "जब तक हम आपको हवा का हाल न बता सकें, तब तक वही सावधानी "
                             "बरतिए जो ख़राब दिन पर बरतते हैं: ज़ोर वाली कसरत घर के अंदर "
                             "कीजिए, और अगर इनहेलर लेते हैं तो साथ रखिए।",
        # Replaces the band advice when the only reading we have is one we are
        # holding. It also accounts for the band, the colour, the risk score
        # and the go-out window all being absent from the same hero.
        "advice_held": "हमें नई माप नहीं मिल सकी, इसलिए इस रीडिंग से यहाँ कुछ भी नहीं "
                       "निकाला गया है: न कोई श्रेणी, न रंग, न ख़तरे का अंक, न बाहर "
                       "निकलने का समय। रीडिंग और उसके मापे जाने का समय नीचे दिया है। "
                       "जब तक हम इसे ताज़ा न कर सकें, तब तक वही सावधानी बरतिए जो ख़राब "
                       "दिन पर बरतते हैं: ज़ोर वाली कसरत घर के अंदर कीजिए, और अगर "
                       "इनहेलर लेते हैं तो साथ रखिए।",
        # risk._BAND_TABLE labels, looked up as 'risk_band_' ~ label.
        "risk_band_Low": "कम",
        "risk_band_Moderate": "मध्यम",
        "risk_band_High": "ज़्यादा",
        "risk_band_Very High": "बहुत ज़्यादा",
        "risk_band_Extreme": "अत्यधिक",
        "baseline_chip": "सेहतमंद बड़ा व्यक्ति, वही काम",
        "window_label": "अगर बाहर जाना ही पड़े",
        "window_note": "यह एक सामान्य पैटर्न है, हर घंटे का पूर्वानुमान नहीं",

        # --- today.html: persona card ---
        "sec_persona": "आपका ब्यौरा",
        # The persona sentence follows, so this ends in a colon rather than
        # wrapping the name the way the English does.
        "advice_for": "यह सलाह इनके लिए है:",
        # First visit: the same slot, but owning up that the persona shown is
        # an example. Two fragments around the highlighted persona phrase,
        # like advice_for above; the second carries the sentence's verb, which
        # Hindi puts after the phrase.
        "example_for_before": "यह पेज अभी एक उदाहरण दिखा रहा है —",
        "example_for_after": "। नीचे अपनी जानकारी भरिए, तो सलाह आपकी अपनी हो जाएगी।",
        # The path from the unreviewed-translation banner into the persona
        # editor, rendered directly under the banner on every Hindi page until
        # a persona is applied.
        "persona_path_lead": "इस साइट की सलाह अभी एक उदाहरण व्यक्ति के लिए लिखी जा रही है।",
        "persona_path_link": "अपनी उम्र, सेहत और इलाक़ा यहाँ चुनिए ›",
        "btn_done": "हो गया",
        "btn_change": "जानकारी बदलें",
        "lbl_age": "उम्र",
        "lbl_condition": "स्वास्थ्य / बीमारी",
        "lbl_activity": "आप क्या करने वाले हैं",
        "lbl_locality": "आप कहाँ हैं",
        # The picker's option labels. Only the label is translated: the value
        # the form submits stays English, because normalize and the query
        # string are keyed on it (see main._option_labels).
        "age_child": "बच्चा",
        "age_adult": "बड़ा व्यक्ति",
        "age_senior": "बुज़ुर्ग",
        "cond_fit": "सेहतमंद",
        "cond_asthma": "अस्थमा",
        "cond_heart": "दिल की बीमारी",
        "cond_pregnancy": "गर्भावस्था",
        "cond_copd": "COPD",
        "act_outdoor_exercise": "बाहर कसरत",
        "act_commute": "आना-जाना",
        "act_school_run": "स्कूल छोड़ना-लाना",
        "act_stay_home": "घर पर रहना",
        "btn_update": "सलाह अपडेट करें",
        "hint_session": "यह सिर्फ़ इसी सेशन में रहता है — कहीं दर्ज नहीं होता।",
        "link_score": "स्कोर कैसे निकाला जाता है, देखिए ›",
        "risk_notice": "इस स्कोर में मेहनत वाला हिस्सा प्रकाशित साँस लेने की दरों से आता है "
                       "(US EPA, जिसका भरोसा मध्यम आँका गया है)। बीमारी और उम्र वाला हिस्सा "
                       "हमारा अपना आकलन है, कोई जाँचा-परखा मेडिकल मॉडल नहीं।",

        # --- today.html: reading card ---
        "sec_reading": "रीडिंग",
        # One key per case, because the caption is a CLAIM about what was
        # measured. It used to be a single unconditional string and said both
        # particulates over a reading built from one.
        "cpcb_scale_both": "भारत का CPCB पैमाना, PM2.5 और PM10 से",
        "cpcb_scale_pm25": "भारत का CPCB पैमाना, सिर्फ़ PM2.5 से — यहाँ PM10 दर्ज नहीं हुआ",
        "cpcb_scale_pm10": "भारत का CPCB पैमाना, सिर्फ़ PM10 से — यहाँ PM2.5 दर्ज नहीं हुआ",
        "scale_low": "0 अच्छी",
        "scale_high": "गंभीर 500",
        "link_numbers": "इन नंबरों का मतलब क्या है? ›",
        # Under the WHO comparison, which is a caveat on the band meaning:
        # the route from a demoted line to the section that explains it.
        "link_who": "यह तुलना कैसे की जाती है ›",
        "dominant_tag": "मुख्य",
        # Printed after "<day> " in the page-loaded clock line.
        "month_1": "जन",
        "month_2": "फ़र",
        "month_3": "मार्च",
        "month_4": "अप्रैल",
        "month_5": "मई",
        "month_6": "जून",
        "month_7": "जुल",
        "month_8": "अग",
        "month_9": "सित",
        "month_10": "अक्तू",
        "month_11": "नव",
        "month_12": "दिस",

        # --- today.html: outlook ---
        "sec_outlook": "पाँच दिन का अनुमान",
        "outlook_title": "अगले पाँच दिन",
        "outlook_caption": "रोज़ का औसत, µg/m³, WAQI के पूर्वानुमान से बदला हुआ — यह मोटा "
                           "अनुमान है, हर घंटे का वादा नहीं।",

        # --- today.html: ask and answers ---
        "sec_ask": "साफ़ साँस से पूछिए",
        # The heading and the section's accessible name say the same thing. The
        # wordmark is written in Devanagari here, not as "SaafSaans": this is a
        # sentence a Hindi reader reads, not the logo.
        "ask_title": "साफ़ साँस से पूछिए",
        # Both of these said the answer itself was written for the reader. What
        # is actually chosen for them is the published guidance behind it, so
        # the Hindi says that too -- neither more nor less than the English.
        "ask_sub": "ऊपर दी गई रीडिंग पर आधारित · आपकी स्थिति के हिसाब से चुनी गई गाइडेंस",
        "ask_placeholder": "बाहर जाने, मास्क, समय या लक्षणों के बारे में पूछिए…",
        "ask_label": "आपका सवाल",
        "btn_ask": "पूछें",
        # The four suggested-question chips. Fixed sentences, not free text --
        # each one is the exact question the input is seeded with, so the
        # Hindi must match the English question mark-for-mark, not merely the
        # topic.
        "ask_chips_label": "सुझाए गए सवाल",
        "ask_chip_outside_now": "क्या अभी बाहर जाना सुरक्षित है?",
        "ask_chip_mask_today": "क्या मुझे आज मास्क पहनना चाहिए?",
        "ask_chip_best_time": "आज बाहर जाने का सबसे अच्छा समय कौन सा है?",
        "ask_chip_symptoms": "कौन से लक्षण होने पर मुझे वापस अंदर चले जाना चाहिए?",
        "ask_hint": "पूछने के लिए एंटर दबाइए। हर जवाब के पीछे की प्रकाशित गाइडेंस ऊपर दी गई "
                    "जानकारी के हिसाब से चुनी जाती है — किसी और के लिए गाइडेंस चाहिए तो "
                    "जानकारी बदल दीजिए।",
        "answered_for": "जवाब इनके लिए:",
        # Marks the reader's own question in the transcript. "प्र" is the
        # standard Hindi abbreviation for प्रश्न, matching the English "Q".
        "q_mark": "प्र ·",
        # The heading on the first block of an answer, and on the block the
        # error path renders. One key, because it is one word on one card.
        "stale_note": "इस इलाक़े के लिए दोनों में से कोई भी स्रोत जवाब नहीं दे रहा, इसलिए आपको "
                      "दिखाने के लिए हमारे पास कोई आँकड़ा नहीं है। पहले यह पेज उस कमी को इस जगह "
                      "के एक आम अनुमान से भर देता था; अब नहीं भरता, क्योंकि बिना मापा हुआ आँकड़ा "
                      "कोई आँकड़ा न होने से भी बुरा है। किसी स्रोत के लौटते ही यह अपने आप बदल जाएगा।",
        # The forwarded-link preview. Placeholders are substituted with
        # str.replace, not .format, so a stray brace cannot raise on a path
        # that runs on every page render.
        "share_site_title": "साफ़ साँस — दिल्ली की हवा, आपके शरीर के हिसाब से",
        "share_site_desc": "देखिए कि आज आपके इलाक़े की हवा आपके लिए क्या मायने रखती है, "
                           "आसान भाषा में।",
        "no_obs_time": "रीडिंग का समय नहीं है",
        "share_title": "{place} की हवा आज: {band}",
        "share_no_reading": "{place}: अभी कोई रीडिंग नहीं है",
        # Why the five-day outlook is missing. It comes from the WAQI forecast,
        # and a reading read from CPCB directly carries none -- so the section
        # is absent for most readers and returns whenever the fallback fires.
        "outlook_absent": "पाँच दिन का अनुमान WAQI फ़ीड से आता है। इस रीडिंग के साथ कोई "
                          "अनुमान नहीं आया, इसलिए दिखाने को कुछ नहीं है — सीधे CPCB से ली गई "
                          "रीडिंग के साथ अनुमान कभी नहीं आता।",
        # Names no band, for the same reason the hero does not.
        "share_held": "{place}: हम एक पुरानी हवा की रीडिंग सहेजे हुए हैं",
        "share_for": "यह सलाह {who} के लिए है।",
        "heading_verdict": "फ़ैसला",
        "heading_what_to_do": "क्या करें",
        "heading_seek_help": "डॉक्टर को कब दिखाएँ",
        "refusal_title": "इस पर कार्रवाई नहीं की गई।",
        "refusal_body": "यह सहायक के काम करने का तरीक़ा बदलने की कोशिश जैसा लगा, इसलिए इसे "
                        "मॉडल तक पहुँचने से पहले ही रोक दिया गया। हवा, बचाव, मास्क, समय — "
                        "इन सब पर बेझिझक पूछिए।",
        # Names the same log the Guide's privacy answer names ("सुरक्षा लॉग"),
        # so a reader who follows one to the other finds the same thing.
        "refusal_audit": "मॉडल तक पहुँचने से पहले रोका गया · सुरक्षा लॉग में दर्ज",
        # today.html, when /ask is rate limited. Deliberately not phrased as
        # an accusation or an error: the reader did nothing wrong, and what
        # they need is the wait, not an apology.
        "throttled_title": "अभी बहुत सारे सवाल आ गए।",
        "throttled_body": "यह एक छोटी मुफ़्त सेवा है, एक ही मशीन पर चलती है, "
                          "इसलिए सवालों की एक सीमा है। आपके सवाल में कोई गड़बड़ "
                          "नहीं थी — कुछ मिनट बाद दोबारा पूछिए, चला जाएगा।",
        "throttled_wait": "दोबारा कोशिश कीजिए लगभग",
        "throttled_minutes": "मिनट में",
        "disclaimer": "यह सामान्य जानकारी है, डॉक्टरी सलाह नहीं।",
        # base.html footer, on every page. Not softened in Hindi: a reader who
        # only reads the Hindi must be told exactly what the English reader is.
        "footer_not_a_device": "यह एक प्रदर्शन परियोजना है — कोई मेडिकल डिवाइस "
                               "नहीं, और आपके डॉक्टर की सलाह का विकल्प नहीं।",
        # main.py, when an answer cannot be built. Carries a safe default
        # instruction, so it must not be shortened to an apology.
        "answer_error": "आपकी सलाह तैयार करने में कुछ गड़बड़ हो गई। शक हो तो बाहर कम से कम "
                        "निकलिए और बाहर N95 पहनिए।",

        # --- today.html: provenance panel ---
        "prov_label": "यह जवाब किस पर आधारित है",
        # The source count is printed between the two.
        "prov_count_before": "1 लाइव रीडिंग +",
        # No reading at all, so no count: the fallback carries no numbers.
        # This key used to read "1 नमूना रीडिंग +" and counted a sample that
        # the app no longer has.
        "prov_count_before_none": "कोई रीडिंग नहीं +",
        # Real numbers, but fetched earlier: the source did not answer this
        # time and we are still holding what it last published.
        "prov_count_before_held": "1 सहेजी हुई रीडिंग +",
        "prov_count_after": "गाइडेंस स्रोत",
        "prov_measured": "उस समय मापा गया",
        # The kicker used to be unconditional and sat above a row of dashes.
        "prov_not_measured": "उस समय कुछ भी मापा नहीं गया",
        "prov_measured_held": "पहले मापा गया था, उस समय नहीं",
        "prov_published": "इस्तेमाल की गई प्रकाशित गाइडेंस",
        # The two groups inside that list: chosen for the reader's own
        # condition, activity or age, and chosen for the air alone.
        "prov_group_persona": "आपकी स्थिति के लिए लिखी गई",
        "prov_group_general": "इस हवा के लिए आम गाइडेंस",
        # The reading's own provenance line, printed as fragments around the
        # numbers: "AQI 250 (CPCB पैमाना ...) · मुख्य प्रदूषक PM25 · ...".
        # US EPA keeps its Latin initials: it is the agency that publishes the
        # scale, and a reader checking the figure needs the name it is filed
        # under.
        "prov_our_scale_both": "(CPCB पैमाना, PM2.5 और PM10 से)",
        "prov_our_scale_pm25": "(CPCB पैमाना, सिर्फ़ PM2.5 से)",
        "prov_our_scale_pm10": "(CPCB पैमाना, सिर्फ़ PM10 से)",
        "prov_dominant": "मुख्य प्रदूषक",
        "prov_feed_figure": "WAQI का अपना आँकड़ा",
        "prov_feed_scale": "(US EPA पैमाना)",
        # Printed around <span lang="en">data.gov.in</span>. The domain stays
        # out of the string: it is an address, not copy.
        "prov_source_cpcb_before": "सीधे CPCB से लिया गया, प्रकाशित",
        "prov_source_cpcb_after": "पर — किसी फ़ीड के ज़रिए नहीं",
        "prov_live": "लाइव रीडिंग",
        "prov_none": "कोई रीडिंग नहीं (किसी भी स्रोत ने जवाब नहीं दिया)",
        "prov_held": "सहेजी हुई रीडिंग (नई रीडिंग नहीं मिल सकी, इसलिए हमने पिछली रखी है)",

        # --- system.html ---
        # This view was left in English on the grounds that it is
        # developer-facing. The nav link that reaches it says सिस्टम and the
        # review banner renders on it, so a Hindi reader is invited in and then
        # met with a wall of English; the decision is reversed here.
        #
        # Register: flat and factual, not the Today page's warm voice. The page
        # is an audit surface, so it states what happened and nothing more.
        #
        # What stays Latin on this page is not listed here at all: event names,
        # guard pattern names and status values are the literal strings stored
        # in the telemetry and security indices, and this view exists to show
        # what is in them. A translated index value would be a description of
        # the data rather than a view of it.
        "sys_sub": "ऐप ख़ुद की जाँच करता है — आँकड़ों पर टिका, गड़बड़ी को छिपाता नहीं, और "
                   "पहरे में। यहीं देखिए।",
        "sys_view_label": "सिस्टम व्यू",
        "sys_view_obs": "निगरानी",
        "sys_view_sec": "सुरक्षा",
        # KPI labels. Each sits under a Latin numeral, so it is a noun phrase,
        # not a sentence.
        "sys_kpi_answered": "सवालों के जवाब दिए गए",
        "sys_kpi_events": "दर्ज घटनाएँ",
        "sys_kpi_p50": "बीच का (मध्यक) जवाब समय",
        # Spelled out rather than left as "p95": a Latin token of that shape is
        # jargon in either language, and the Hindi names the thing it measures.
        "sys_kpi_p95": "95वाँ प्रतिशतक जवाब समय",
        "sys_kpi_feed_fallback": "फ़ीड नहीं मिली → कोई रीडिंग नहीं",
        "sys_kpi_rule_fallback": "नियम-आधारित जवाब",
        "sys_kpi_tokens": "ख़र्च हुए टोकन",
        "sys_kpi_blocked_7d": "रोकी गईं, पिछले 7 दिन",
        "sys_kpi_premodel": "मॉडल से पहले रुकीं",
        "sys_kpi_patterns": "अलग-अलग पैटर्न",
        # --- observability ---
        "sys_h_events": "प्रकार के हिसाब से घटनाएँ",
        "sys_events_caption": "फ़ॉलबैक दर्ज होते हैं, छिपाए नहीं जाते — सहेजी हुई रीडिंग या "
                              "नियम-आधारित जवाब जिस समय दिया जाता है, उसी समय वैसा ही "
                              "बताया जाता है।",
        # The shell command is printed after this fragment, so the Hindi ends
        # where the command begins.
        "sys_empty_telemetry": "अभी तक कोई टेलीमेट्री नहीं है। ‘आज’ पर कोई सवाल पूछिए, या "
                               "पुराना डेटा भरने के लिए यह चलाइए:",
        # "जवाब नहीं दे रहा", not "सेट नहीं है": a configured endpoint that is
        # down records exactly as much as no endpoint at all, and the page must
        # not name a cause it has not checked.
        "sys_empty_no_index": "यह हिस्सा एक डेटाबेस इंडेक्स से डेटा पढ़ता है, और अभी "
                              "कोई इंडेक्स जवाब नहीं दे रहा, इसलिए कुछ भी दर्ज नहीं हो रहा। "
                              "ऐप इसके बिना भी चलता है; बस ये पैनल नहीं चलते।",
        "sys_h_localities": "इलाक़े के हिसाब से रिक्वेस्ट",
        "sys_empty_localities": "अभी तक इलाक़े का कोई डेटा नहीं है।",
        # The row labels are the pixel ranges themselves, in figures, so they
        # need no translation and cannot drift from app.css in one language
        # only.
        "sys_h_viewport": "ब्राउज़र की चौड़ाई के हिसाब से पेज लोड",
        # "दर्ज होते हैं" -- what is WRITTEN DOWN. Not "कोई पता नहीं", which
        # reads first as the idiom "no idea" and only second as "no address";
        # "कोई आईपी पता दर्ज नहीं होता" says the thing meant, and matches the
        # narrower claim: the address exists in memory for a few minutes as a
        # rate-limit key, so what is honest is what is STORED, not what never
        # existed.
        #
        # "फ़र्श" (floor) is the load-bearing word: the count is a lower bound.
        # An earlier draft said automated visits are counted like people, which
        # is backwards -- this mechanism only counts a client that fetches the
        # stylesheet's image, and most bots never do.
        "sys_viewport_caveat": "पेज लोड, लोग नहीं: सिर्फ़ चौड़ाई की श्रेणी और समय दर्ज "
                               "होते हैं — कोई कुकी नहीं, कोई आईपी पता दर्ज नहीं होता, "
                               "कोई पहचान नहीं। यह ब्राउज़र विंडो की चौड़ाई है, डिवाइस "
                               "का प्रकार नहीं। इसे कम से कम की गिनती मानिए, कुल नहीं: "
                               "गिनती तभी होती है जब ब्राउज़र स्टाइलशीट की तस्वीर लाता "
                               "है, इसलिए तस्वीरें रोकने वाले ब्राउज़र, बैक बटन से खुले "
                               "पेज और ज़्यादातर अपने आप चलने वाले प्रोग्राम इसमें नहीं "
                               "आते, जबकि आकार बदली हुई विंडो और लिंक का पूर्वावलोकन "
                               "दो-दो बार गिने जा सकते हैं।",
        "sys_empty_viewport": "अभी तक कोई पेज लोड नहीं गिना गया।",
        "sys_empty_viewport_no_index": "यह नापा हुआ शून्य नहीं है: यह इंडेक्स जवाब नहीं "
                                       "दे रहा, इसलिए ब्राउज़र की चौड़ाई दर्ज नहीं हो रही।",
        # --- security ---
        "sys_h_blocked_7d": "रोकी गईं · पिछले 7 दिन",
        "sys_empty_blocked_7d": "पिछले 7 दिनों में रोकी गई कोई कोशिश दर्ज नहीं है।",
        # The KPI beside this chart reads 0 in both states. This one is the
        # unrecorded zero, not the measured one.
        "sys_empty_blocked_7d_no_index": "यह नापा हुआ शून्य नहीं है: कोई डेटाबेस इंडेक्स "
                                         "जवाब नहीं दे रहा, इसलिए रोकी गई कोशिशें दर्ज "
                                         "नहीं होतीं।",
        "sys_h_attempts": "हाल में रोकी गई कोशिशें",
        "sys_btn_simulate": "रेड-टीम सिमुलेशन चलाइए",
        # The attack count is printed between these two.
        "sys_sim_note_before": "सिमुलेशन ने गार्ड पर",
        "sys_sim_note_after": "जानी-पहचानी हमलावर प्रॉम्प्ट चलाईं — सभी मॉडल तक पहुँचने से "
                              "पहले रोक दी गईं, नीचे दर्ज हैं।",
        # The index answers but nothing it returned is listed. This variant
        # stops at the block itself and makes no claim about the log; the
        # empty state below it says why the list is empty.
        "sys_sim_note_after_unlisted": "जानी-पहचानी हमलावर प्रॉम्प्ट चलाईं — सभी मॉडल तक "
                                       "पहुँचने से पहले रोक दी गईं।",
        # The no-index variant. It must not claim anything was logged: with no
        # database index the guard still blocks, but nothing is recorded, and
        # the empty state below says so.
        "sys_sim_note_after_no_index": "जानी-पहचानी हमलावर प्रॉम्प्ट चलाईं — सभी मॉडल तक "
                                       "पहुँचने से पहले रोक दी गईं। कोई डेटाबेस इंडेक्स "
                                       "जवाब नहीं दे रहा, इसलिए इनमें से कुछ भी नीचे दर्ज "
                                       "नहीं हुआ।",
        # Follows the count of blocked prompts in one pattern group.
        "sys_blocked_premodel": "बार रोकी गईं · मॉडल से पहले",
        # Sits under the list of blocked attempts and explains why the text
        # above it is not in Hindi. It must not say the attempt is shown
        # "जैसा आया था" -- normalize.excerpt cuts at 120 characters, and the
        # simulation button on this page fires a ~1,250-character attack.
        "sys_excerpt_caption": "जिस भी भाषा में यह लिखा गया था, उसी में दिखाया गया है, "
                               "और इसका अनुवाद कभी नहीं किया जाता। लंबी कोशिशें काटकर "
                               "दिखाई जाती हैं।",
        "sys_empty_attempts": "अभी तक कुछ रोका नहीं गया है। ऊपर सिमुलेशन चलाइए, या ‘आज’ से "
                              "कोई इंजेक्शन कोशिश भेजिए — दोनों ही सूरत में वह यहाँ दर्ज होगी।",
        # Shown after a run, where "अभी तक कुछ रोका नहीं गया है" would
        # contradict the note above it and the remedy it offers is the run
        # that produced this screen.
        "sys_empty_attempts_after_sim": "दिखाने को कुछ नहीं: इंडेक्स जवाब दे रहा है, पर "
                                        "इस पेज पर दिखाई जा सकने वाली कोई रोकी गई "
                                        "प्रॉम्प्ट उसने नहीं लौटाई।",
        # The no-index variant drops both remedies above: with nothing
        # answering, neither the simulation nor a question from Today is
        # recorded anywhere, so offering them would be a wrong remedy.
        "sys_empty_attempts_no_index": "यहाँ कुछ भी दर्ज नहीं हो रहा: कोई डेटाबेस इंडेक्स "
                                       "जवाब नहीं दे रहा। गार्ड इन प्रॉम्प्ट को फिर भी "
                                       "रोकता है — बस यह सूची नहीं चलती।",
    },
    # The Guide's own prose. Keys are the strings guide.html asks for, in page
    # order: ``h_*`` headings, ``th_*`` table headers, ``q_*``/``a_*`` FAQ pairs
    # named after the question rather than numbered.
    "guide": {
        "sub": "इस साइट का हर नंबर और हर शब्द, आसान भाषा में।",
        "h_numbers": "नंबर",
        "h_conditions": "पिकर में दी गई बीमारियाँ",
        # The two glossary terms the Guide's number table names in its own
        # words. The definitions live in the ``glossary`` group.
        "term_dominant": "मुख्य प्रदूषक",
        "term_risk_score": "जोखिम स्कोर",

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
        # The mirror of guide.html's a_data_source, and it was stale in its own
        # separate way: it promised the last good reading tagged ‘सहेजी हुई’ on
        # the home page, which that page never did, AND the deleted ‘नमूना’
        # stand-in. Both gone. The tag words here are the same two the pages
        # print (``tag_cached``, ``tag_no_reading``), which is what
        # test_guide_describes_the_tags_the_app_actually_prints checks.
        "a_data_source_before": "भारत के CPCB नेटवर्क के ज़मीनी निगरानी स्टेशनों से। पहले हम "
                                "CPCB का अपना प्रकाशन पढ़ते हैं, सरकार की खुली डेटा साइट",
        "a_data_source_after": " पर; और जब वहाँ किसी जगह के लिए कुछ न हो, तब WAQI फ़ीड से, जो "
                               "इसी नेटवर्क को दोबारा छापती है। जब दोनों में से कहीं भी कुछ न "
                               "मिले, तो उस जगह का कोई नंबर नहीं दिखाया जाता: वह हमारे पास है "
                               "ही नहीं, और हम उसे गढ़ेंगे नहीं। अगर उस जगह की कोई पुरानी माप "
                               "हमारे पास है, तो हम बताते हैं कि वह कितनी थी और कब ली गई "
                               "थी — और उससे और कुछ नहीं निकाला जाता: न श्रेणी का नाम, न रंग, "
                               "न ख़तरे का अंक, न बाहर निकलने का समय। यह ‘आज’ वाले पेज पर भी "
                               "उतना ही लागू होता है जितना शहर की नब्ज़ पर। शहर की नब्ज़ पर ‘सहेजी हुई’ टैग उस रीडिंग पर लगता है जो "
                               "हमारे पास पहले से है और हम उसे ही दिखा रहे हैं — अभी-अभी आई "
                               "हुई नहीं — और साथ में यह भी लिखा होता है कि माप कितना पुराना "
                               "है; और जिस जगह की कोई रीडिंग हमारे पास है ही नहीं, उस पर ‘कोई "
                               "रीडिंग नहीं’ लिखा होता है। पुरानी चीज़ को कभी लाइव बनाकर नहीं "
                               "दिखाया जाता।",
        "q_ignores": "जवाब कभी-कभी मेरे सवाल को अनदेखा क्यों कर देता है?",
        "a_ignores": "जवाब उसी व्यक्ति के लिए लिखे जाते हैं जो ‘आज’ वाले पेज पर दिखाया गया है, "
                     "किसी काल्पनिक व्यक्ति के लिए नहीं। ‘अगर मैं सेहतमंद होता तो?’ पूछने पर भी "
                     "सलाह उसी व्यक्ति के लिए आएगी जो आपने चुना है। व्यक्ति बदलिए और दोबारा "
                     "पूछिए — पूरा पेज, जवाब समेत, आपके चुने हुए व्यक्ति के लिए फिर से लिखा "
                     "जाता है।",
        "q_privacy": "मैं जो टाइप करता हूँ उसका क्या होता है?",
        "a_privacy": "आपकी उम्र, बीमारी और आपके काम पेज के पते और आपके सेशन में रहते हैं — ये "
                     "कभी किसी डेटाबेस में नहीं लिखी जातीं। आपके इस ब्यौरे में से सिर्फ़ आपका "
                     "चुना हुआ इलाक़ा जानबूझकर रखा जाता है, ताकि सिस्टम व्यू दिखा सके कि किन इलाक़ों "
                     "से रिक्वेस्ट आती हैं; उसे कभी आपकी बीमारी के साथ नहीं रखा जाता। सवालों की "
                     "जाँच होती है कि कहीं वे मॉडल को बरगलाने की कोशिश तो नहीं, उसके बाद ही वे "
                     "मॉडल तक जाते हैं। लॉग में एकतरफ़ा हैश किया हुआ सेशन आईडी और स्टेटस रहते "
                     "हैं; सुरक्षा लॉग में रोके गए सवाल का ज़्यादा से ज़्यादा 120 अक्षर का "
                     "टुकड़ा रखा जाता है। इनसे अलग, हर पेज लोड पर आपका ब्राउज़र जो चौड़ाई "
                     "बताता है वह गिनी जाती है — सिर्फ़ चौड़ाई की श्रेणी और समय, न कोई "
                     "सेशन आईडी और न कुछ और।",
        "q_medical": "क्या यह डॉक्टरी सलाह है?",
        "a_medical": "नहीं। यह सार्वजनिक स्वास्थ्य स्रोतों (CPCB, WHO, GINA, GOLD, AHA, ACOG, "
                     "EPA) से बनी सामान्य जानकारी है। अगर आपकी तबीयत ठीक नहीं है, या आपकी रोज़ "
                     "की दवा पहले जैसा काम नहीं कर रही, तो डॉक्टर से संपर्क कीजिए।",

        "h_scale": "हवा का नंबर कहाँ से आता है, और वह क्या नहीं है",
        "scale_1": "रीडिंग भारत के CPCB निगरानी स्टेशनों से आती हैं। ज़्यादातर वैसे ही "
                   "पहुँचती हैं जैसे CPCB उन्हें छापता है: सांद्रता में, उन्हीं इकाइयों में जो "
                   "यंत्र दर्ज करता है। कुछ WAQI फ़ीड के ज़रिए आती हैं, जो इसी नेटवर्क को "
                   "दोबारा छापती है। WAQI अपने नंबर अमेरिका के EPA सूचकांक पर छापता है, भारत के "
                   "नहीं — उसने जनवरी 2016 में हर भारतीय स्टेशन को अमेरिकी पैमाने पर कर दिया "
                   "था, और वह ख़ुद कहता है कि इसीलिए उसके आँकड़े भारत के अपने राष्ट्रीय AQI "
                   "पोर्टल से अलग होंगे।",
        "scale_2": "दोनों पैमानों में बड़ा फ़र्क़ है। 60 µg/m³ PM2.5 भारत के पैमाने पर 100 "
                   "यानी ‘संतोषजनक’ है, और अमेरिकी पैमाने पर क़रीब 154 यानी वहाँ की "
                   "‘सेहत के लिए हानिकारक’ श्रेणी। "
                   "इसीलिए जो रीडिंग WAQI फ़ीड से आई है उसे बदला जाता है: उसके अमेरिकी "
                   "सूचकांक को वापस सांद्रता में बदला जाता है, फिर उससे भारतीय आँकड़ा निकाला "
                   "जाता है। जो रीडिंग सीधे CPCB से पढ़ी गई है वह पहले से ही सांद्रता में आती "
                   "है और उसे इस बदलाव से कभी नहीं गुज़ारा जाता। दोनों हालात में यहाँ दिखने "
                   "वाला नंबर वैसा ही होता है जैसा दिल्ली में बाक़ी हर जगह दिखता है।",
        "scale_3": "वह नंबर क्या नहीं है। यह सिर्फ़ कणों से निकाला जाता है — PM2.5 और PM10 "
                   "से, और कभी-कभी इन दोनों में से सिर्फ़ एक से, जो ‘आज’ वाले पेज पर रीडिंग "
                   "के साथ ही लिखा होता है। भारत का "
                   "सरकारी तरीक़ा आठ तक प्रदूषकों का इस्तेमाल करता है और कम से कम तीन माँगता "
                   "है, इसलिए जिस दिन ओज़ोन जैसी कोई गैस हवा में सबसे ख़राब चीज़ हो, उस दिन "
                   "सरकारी आँकड़ा हमारे आँकड़े से ज़्यादा होगा। जिस जवाब के साथ कोई रीडिंग "
                   "होती है, उसके नीचे दिया गया "
                   "स्रोत पैनल बताता है कि रीडिंग दोनों में से किस स्रोत से आई है, और WAQI का "
                   "अपना आँकड़ा तभी दिखाता है जब रीडिंग WAQI से ही आई हो।",

        "h_who": "विश्व स्वास्थ्य संगठन से तुलना",
        # The figure and its unit are printed in bold between these three, so
        # the Hindi names the guideline first and states the value after the
        # colon. ``who_1_after`` follows the bold run with no separator.
        "who_1_before": "PM2.5 के लिए संगठन की गाइडलाइन:",
        "who_1_unit": "µg/m³, 24 घंटे के औसत पर",
        "who_1_after": "। और साल भर के औसत पर 5 µg/m³। ‘आज’ वाले पेज की पंक्ति यही तुलना "
                       "करती है। वह किससे तुलना कर रही है, यह इस पर निर्भर करता है कि रीडिंग "
                       "कहाँ से आई, और दोनों एक चीज़ नहीं हैं: CPCB 24 घंटे का औसत छापता है, "
                       "और WAQI फ़ीड पिछले एक घंटे का आँकड़ा, जो पूरे दिन का औसत है ही नहीं।",
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
        # The age bands the source's table is published for. "<11" is written
        # out as "11 साल से कम" because Hindi puts the comparison after the
        # number, and a bare "<" before a numeral reads as a stray glyph.
        "age_band_child": "6 से 11 साल से कम",
        "age_band_adult": "21 से 31 साल से कम",
        "age_band_senior": "61 से 71 साल से कम",
        # The four exertion levels, printed inside "बाहर कसरत = ज़्यादा".
        "level_sedentary": "बैठे-बैठे",
        "level_light": "हल्का",
        "level_moderate": "मध्यम",
        "level_high": "ज़्यादा",
        "mapping_ours": "आपके किस काम को कितनी मेहनत माना जाए, यह हमारा अपना आकलन है, स्रोत "
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
        # The disclaimer printed as the "source" of the judgement table. It
        # denies three separate things -- validation, derivation, and any
        # published model -- and the Hindi keeps all three, because a reader
        # who loses one of them reads the table as evidence.
        "source_unvalidated": "बिना जाँचा-परखा क्लिनिकल अनुमान। सिर्फ़ आपसी क्रम बताने के लिए, "
                              "जिसे लेखक ने सामान्य सार्वजनिक-स्वास्थ्य गाइडेंस से चुना है; यह "
                              "किसी प्रकाशित जोखिम मॉडल से न तो निकाला गया है, न उसके सामने "
                              "परखा गया है।",
        "open_code": "अगर आपको लगता है कि यहाँ का संतुलन ग़लत है, तो आप हर आँकड़ा देख भी "
                     "सकते हैं और बदल भी सकते हैं — पूरा हिसाब सौ पंक्तियों के पढ़े जा सकने "
                     "वाले कोड में है, और उसमें आपसे कुछ भी छिपाया नहीं गया।",
    },
    # presenters.persona_sentence -- the reader described back to themselves.
    #
    # The pieces compose as "{who}, {condition}, {place} में {activity}", so the
    # condition is a relative clause ("जिसे अस्थमा है") and the activity a
    # predicate that closes the sentence ("बाहर कसरत करने वाले हैं"). It was a
    # noun phrase built on "योजना", which left the sentence without a verb and
    # used a word that reads as a scheme rather than an intention. English puts
    # the place last; Hindi puts it before the activity, which is why the frames
    # below are whole strings with reordered fields, not fragments joined in code.
    "persona": {
        "age_child": "एक बच्चा",
        "age_adult": "एक बड़ा व्यक्ति",
        "age_senior": "एक बुज़ुर्ग",
        "condition_fit": "जो सेहतमंद है",
        "condition_asthma": "जिसे अस्थमा है",
        "condition_heart": "जिसे दिल की बीमारी है",
        "condition_pregnancy": "जो गर्भवती है",
        "condition_copd": "जिसे COPD है",
        "activity_exercise": "बाहर कसरत करने वाले हैं",
        "activity_commute": "बाहर आने-जाने वाले हैं",
        "activity_school_run": "बच्चे को स्कूल छोड़ने-लाने वाले हैं",
        "activity_stay_home": "घर पर ही रहने वाले हैं",
        "with_activity_and_place": "{who}, {condition}, {place} में {activity}",
        "with_activity": "{who}, {condition}, {activity}",
        "with_place": "{who}, {condition}, {place} में",
        "plain": "{who}, {condition}",
        # The hero's kicker. ``.upper()`` runs over this in every language and
        # leaves Devanagari untouched.
        "kicker": "इनके लिए: {persona}",
    },
    # presenters.city_summary -- the City Pulse subtitle.
    #
    # A whole sentence per form, not the fragments the page used to interleave.
    # Hindi puts the total first ("21 में से"), which no fixed English assembly
    # order can produce, and the two forms exist because a median computed over
    # zero readings is not a median -- the page used to print one anyway, off
    # stand-in figures, and read "21 स्टेशन · बीच का (मध्यक) AQI 358" while
    # holding nothing at all.
    "city": {
        # {n} in `summary` is the number reporting NOW, and the median is
        # taken across those alone -- the sentence says so, because a median
        # over one stale figure was being read as the city's.
        "summary": "{total} में से {n} स्टेशन अभी रीडिंग भेज रहे हैं · पेज लोड होने का समय "
                   "{now} · उन {n} का बीच का (मध्यक) AQI {median} · सबसे ख़राब पहले",
        "summary_stale": "अभी कोई स्टेशन रीडिंग नहीं भेज रहा · {total} में से {n} स्टेशन की "
                         "पहले की रीडिंग हमारे पास है · पेज लोड होने का समय {now} "
                         "· सबसे ख़राब पहले",
        "summary_none": "{total} में से किसी भी स्टेशन की रीडिंग अभी हमारे पास नहीं है "
                        "· पेज लोड होने का समय {now}",
    },
    # presenters.comparison_line -- the gap to a healthy adult.
    #
    # The three commitments the English makes are kept: the comparison person
    # has the reader's OWN plans, the gap is attributed to the body, and the
    # plans are never denied outright.
    "compare": {
        "reason_asthma": "आपके अस्थमा",
        "reason_heart": "आपके दिल की बीमारी",
        "reason_pregnancy": "आपकी गर्भावस्था",
        "reason_copd": "आपके COPD",
        "reason_condition": "आपकी बीमारी",
        "reason_child": "आपके बच्चा होने",
        "reason_senior": "आपके बुज़ुर्ग होने",
        # Joins the reasons, which the sentence then follows with "की वजह से",
        # so the last item must not carry its own postposition.
        "reason_join": " और ",
        "gap_with_reasons": "आपके जैसे ही काम करने वाला एक सेहतमंद बड़ा व्यक्ति {baseline} पर होता। "
                            "आपका {score} {reasons} की वजह से है — यह फ़र्क़ आपके शरीर का है, "
                            "हवा का नहीं।",
        "gap_plain": "आपके जैसे ही काम करने वाला एक सेहतमंद बड़ा व्यक्ति {baseline} पर होता। आपका "
                     "{score} उससे ज़्यादा है।",
        "same": "आपके जैसे ही काम करने वाला एक सेहतमंद बड़ा व्यक्ति भी {baseline} पर ही होता — आज आप "
                "वही हैं।",
    },
    # risk.compute_risk -- the driver chips under the score.
    "driver": {
        # ``{band}`` is filled from band_label, whose values are adjectives
        # ("ख़राब"), so the chip is phrased "हवा {band}" rather than putting the
        # word in brackets the way English does.
        "aqi": "AQI {aqi} — हवा {band}",
        "no_reading": "कोई रीडिंग नहीं — हवा ख़राब मानी गई",
        "cond_asthma": "अस्थमा से ख़तरा बढ़ता है",
        "cond_heart": "दिल की बीमारी से ख़तरा बढ़ता है",
        "cond_pregnancy": "गर्भावस्था से ख़तरा बढ़ता है",
        "cond_copd": "COPD से ख़तरा बढ़ता है",
        "act_outdoor_exercise": "बाहर की मेहनत से हवा कई गुना अंदर जाती है",
        "act_commute": "आने-जाने में बाहर की हवा ज़्यादा लगती है",
        "act_school_run": "स्कूल छोड़ने-लाने में बाहर की हवा ज़्यादा लगती है",
        "age_child": "बच्चों पर असर ज़्यादा होता है",
        "age_senior": "बुज़ुर्गों पर असर ज़्यादा होता है",
    },
    # forecast.best_window -- the "if you must go out" bar and its reasoning.
    #
    # Clock times are written as Hindi phrases with Latin digits ("सुबह 6 से 9
    # बजे") rather than as "6-9 AM": the page prints no AM/PM anywhere else in
    # Hindi, and the 12-hour marker is not what a Delhi reader says out loud.
    "window": {
        "none": "आज बाहर के लिए कोई सुरक्षित समय नहीं",
        # forecast.best_window names a run of hours, so the clock time is
        # composed by clock_range above and dropped in here. "क़रीब ... तक"
        # is how the four hand-written window strings this replaces framed
        # the same range.
        "today_window": "आज, क़रीब {range} तक",
        "no_named_hour": "आज बचे घंटों में कोई ज़्यादा शांत नहीं है।",
        "none_rationale": "अभी AQI बहुत ख़राब/गंभीर श्रेणी में है, इसलिए प्रदूषण पूरे दिन "
                          "ख़तरनाक बना रहेगा। सबसे अच्छा यही है कि घर के अंदर रहें और "
                          "खिड़कियाँ बंद रखें। यह एक मोटा नियम है, हर घंटे का स्टेशन "
                          "पूर्वानुमान नहीं।",
        "o3_rationale": "आज की हवा में मुख्य चीज़ ओज़ोन है, जो दोपहर की धूप में बनती जाती है — "
                        "इसलिए सुबह-सुबह का समय ज़्यादा साफ़ रहता है और दोपहर सबसे ख़राब।",
        "no2_rationale": "आज की हवा में मुख्य चीज़ गाड़ियों की गैसें (जैसे NO2) हैं, जो सुबह "
                         "और शाम की भीड़ के समय एकदम बढ़ जाती हैं — इसलिए इनके बीच का दोपहर "
                         "वाला ठहराव ज़्यादा शांत रहता है।",
        "winter_rationale": "मुख्य चीज़ बारीक कण हैं। दिल्ली की सर्दी में रात भर का तापमान "
                            "उलटाव धुंध को ज़मीन के पास दबा देता है, इसलिए क़रीब 6 से 10 बजे "
                            "सुबह सबसे ख़राब रहती है और मिश्रण परत ऊपर उठते ही, दोपहर शुरू "
                            "होते-होते, हवा कुछ हल्की हो जाती है।",
        "default_rationale": "मुख्य चीज़ बारीक कण हैं। सर्दी के अलावा दोपहर की धूप ओज़ोन भी "
                             "बढ़ा देती है, इसलिए दोपहर के चढ़ाव से पहले देर सुबह का समय "
                             "ज़्यादा शांत रहता है।",
        "general_note": "यह एक सामान्य पैटर्न है, हर घंटे का स्टेशन पूर्वानुमान नहीं।",
        "note_poor": "हवा पहले ही ख़राब है, इसलिए बाहर का कोई भी काम कम समय का रखें और N95 "
                     "पहनें।",
        "note_moderate": "हवा मध्यम है, इसलिए ज़ोर वाली मेहनत कम कर दें।",
    },
    # llm._rule_based -- the answer a reader actually gets, sentence by
    # sentence. This is the copy the whole feature exists to deliver, so the
    # instructions here are translated for force, not for elegance: the mask,
    # the purifier and the stop-and-seek-help lines say exactly what the
    # English says, nothing added and nothing dropped.
    "answer": {
        "activity_swimming": "तैराकी",
        "activity_cycling": "साइकिल चलाना",
        "activity_running": "दौड़ना",
        "activity_walking": "टहलना",
        "activity_sport": "बाहर का खेल",
        "activity_generic": "बाहर की गतिविधि",
        "precaution_swimming": "घर के अंदर वाला पूल चुनें; खुले में तैरने का मतलब है सीधे "
                               "प्रदूषित हवा में गहरी साँस लेना, इसलिए पूल बाहर हो तो समय कम "
                               "रखें।",
        "precaution_cycling": "कम ट्रैफ़िक वाले हरे रास्ते चुनें और मुख्य सड़कों से बचें, जहाँ "
                              "साइकिल चलाने वालों के अंदर गाड़ियों का धुआँ सबसे ज़्यादा जाता "
                              "है।",
        "precaution_running": "रफ़्तार धीमी करें और दूरी कम करें; दौड़ते समय की तेज़ साँस बारीक "
                              "कणों को फेफड़ों की गहराई तक खींच लेती है।",
        "precaution_walking": "छाँव वाली, कम ट्रैफ़िक की गलियों से चलें और आराम से चलें।",
        "precaution_sport": "कम समय के सत्र रखें और जहाँ हो सके, घर के अंदर आकर आराम करें।",
        # {activity} is one of the activity_* labels above; {aqi} is a Latin
        # numeral. Hindi puts the activity before the verb, so the fields sit
        # in a different order from the English.
        "why_unknown": "AQI की रीडिंग उपलब्ध नहीं है; पक्का पता चलने तक {activity} को "
                       "असुरक्षित मानें।",
        "why_severe": "AQI {aqi} बहुत ख़राब से गंभीर है; {activity} न करें।",
        "why_unhealthy": "AQI {aqi} सेहत के लिए हानिकारक है; {activity} कम करें और बचाव के "
                         "साथ करें।",
        "why_ok": "AQI {aqi} ठीक-ठाक है; {activity} किया जा सकता है।",
        "generic_advisory": "अभी हवा की गुणवत्ता का डेटा सीमित है; शक हो तो बाहर कम से कम "
                            "निकलें और बाहर N95 पहनें।",
        # Appended straight onto the advisory sentence, so it keeps the leading
        # space the English has.
        "stale_suffix": " (इस इलाक़े की कोई रीडिंग हमारे पास नहीं है)",
        # Not the line above: there IS a reading, it is just not the air now.
        "held_suffix": " (यह हमारी सहेजी हुई पुरानी रीडिंग से है, अभी की हवा से नहीं)",
        "precaution_mask_high": "बाहर अच्छी तरह फ़िट होने वाला N95/FFP2 मास्क पहनें और घर के "
                                "अंदर एयर प्यूरीफ़ायर चलाएँ।",
        "precaution_mask_low": "N95 पास रखें और हवा की गुणवत्ता में बदलाव पर नज़र रखें।",
        "window_none": "आज बाहर के लिए कोई सुरक्षित समय नहीं है; खिड़कियाँ बंद करके और "
                       "प्यूरीफ़ायर चलाकर घर के अंदर रहें।",
        "window_default": "सुबह जल्दी (6 से 9 बजे) और देर शाम आमतौर पर ज़्यादा साफ़ रहती है; "
                          "दोपहर और भीड़ के समय से बचें।",
        "symptom_stop": "सीने में जकड़न, घरघराहट या साँस फूलने लगे तो रुक जाएँ और किसी ढकी हुई "
                        "जगह के अंदर चले जाएँ।",
        "symptom_urgent": "लगातार खाँसी, चक्कर या धड़कन का तेज़ होना भी मतलब है कि तुरंत रुक "
                          "जाएँ।",
    },
    # presenters.who_line -- the comparison with the WHO guideline.
    #
    # The sentence makes NO claim about when. "अभी" ("right now") was removed
    # from all four branches: ADR 0005 measured CPCB's avg_value to be a
    # rolling 24-hour mean, so on the primary path the claim was false. What
    # must survive translation is the guideline being *for a whole day*, with
    # no dose and no daily average claimed of the reading itself, and "गुना"
    # meaning "times as much" rather than "times more than".
    "who": {
        # Printed when there IS an index but no fine-particle figure behind it
        # -- a station reporting PM10 only. The line used to vanish silently.
        # No particulate name and no microgram: this sits on the reading card.
        "no_fine_particles": "विश्व स्वास्थ्य संगठन की तुलना सबसे महीन कणों के बारे में है, और "
                             "यह स्टेशन अभी उन्हें दर्ज नहीं कर रहा, इसलिए वह पंक्ति नहीं "
                             "दिखाई जा रही।",
        "below": "यहाँ की हवा विश्व स्वास्थ्य संगठन के पूरे दिन के सुरक्षित स्तर से साफ़ "
                 "है।",
        "about_at": "यहाँ की हवा क़रीब-क़रीब विश्व स्वास्थ्य संगठन के पूरे दिन के सुरक्षित "
                    "स्तर पर है।",
        "far_more": "यहाँ की हवा में यह प्रदूषण विश्व स्वास्थ्य संगठन के पूरे दिन के "
                    "सुरक्षित स्तर से कहीं ज़्यादा है।",
        "multiple": "यहाँ की हवा में यह प्रदूषण विश्व स्वास्थ्य संगठन के पूरे दिन के "
                    "सुरक्षित स्तर से क़रीब {word} है।",
        # Spelled out, as in the English, so the sentence reads rather than
        # being scanned.
        "multiple_2": "दोगुना",
        "multiple_3": "तीन गुना",
        "multiple_4": "चार गुना",
        "multiple_5": "पाँच गुना",
        "multiple_6": "छह गुना",
        "multiple_7": "सात गुना",
        "multiple_8": "आठ गुना",
        "multiple_9": "नौ गुना",
        "multiple_10": "दस गुना",
        "multiple_20": "बीस गुना",
        "multiple_30": "तीस गुना",
        "multiple_40": "चालीस गुना",
        "multiple_50": "पचास गुना",
        "multiple_60": "साठ गुना",
        "multiple_70": "सत्तर गुना",
        "multiple_80": "अस्सी गुना",
        "multiple_90": "नब्बे गुना",
        "multiple_100": "सौ गुना",
        "multiple_200": "दो सौ गुना",
        "multiple_300": "तीन सौ गुना",
        "multiple_400": "चार सौ गुना",
        "multiple_500": "पाँच सौ गुना",
    },
    # presenters.provenance_chip. The glyph is part of the string: it is the
    # only thing telling the two chips apart at a glance.
    # Delhi locality and region names. These are Hindi place names; a reader who
    # reads only Devanagari cannot read "Anand Vihar" at all, and the metro
    # signs and the newspapers write them this way. The picker's VALUE stays the
    # English string -- it is the key into waqi.FEED_MAP and the query
    # parameter -- and only the label is translated.
    "locality": {
        "Anand Vihar": "आनंद विहार",
        "ITO": "आईटीओ",
        "Rohini": "रोहिणी",
        "RK Puram": "आर.के. पुरम",
        "Punjabi Bagh": "पंजाबी बाग",
        "Mandir Marg": "मंदिर मार्ग",
        "Dwarka": "द्वारका",
        "Najafgarh": "नजफगढ़",
        "Wazirpur": "वज़ीरपुर",
        "Jahangirpuri": "जहांगीरपुरी",
        "Okhla": "ओखला",
        "Ashok Vihar": "अशोक विहार",
        "Nehru Nagar": "नेहरू नगर",
        "Patparganj": "पटपड़गंज",
        "DTU": "डीटीयू",
        "Delhi (city)": "दिल्ली (शहर)",
        "Noida": "नोएडा",
        "Greater Noida": "ग्रेटर नोएडा",
        "Gurugram": "गुरुग्राम",
        "Ghaziabad": "गाज़ियाबाद",
        "Faridabad": "फ़रीदाबाद",
        "Delhi": "दिल्ली",
        "NCR": "एनसीआर",
    },
    "prov": {
        # Was "◌ नमूना — यह माप नहीं है" (sample - this is not a measurement).
        # There is no stand-in figure any more, so there is no sample to name.
        "no_reading": "◌ कोई रीडिंग नहीं",
        "live": "● लाइव · {when}",
        # The same word City Pulse's tag carries, so a reader who learnt it on
        # one page meets it again rather than meeting a synonym.
        "cached": "◌ सहेजी हुई · {when}",
    },
    # presenters.sparkline_svg -- the accessible name of the 24-hour chart.
    #
    # This is the only accessible name on the site that carries data rather
    # than naming a control, and it is the whole chart for a screen-reader
    # user: the SVG's shape says nothing aloud. Left in English it was read to
    # a Hindi reader with Devanagari phonetics. It is not caught by
    # test_hindi_completeness's page scan, which strips attributes wholesale
    # before looking for Latin, so it has its own test.
    "a11y": {
        "spark": "पिछले 24 घंटों का AQI, {lo} से {hi} तक",
    },
    # presenters.outlook_rows -- the five-day strip's row labels.
    "day": {
        "today": "आज",
        # Weekday then date, the same order Hindi uses.
        "label": "{weekday} {date}",
        "mon": "सोम",
        "tue": "मंगल",
        "wed": "बुध",
        "thu": "गुरु",
        "fri": "शुक्र",
        "sat": "शनि",
        "sun": "रवि",
    },
    # data.advisories -- the 43 seeded health advisories.
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
            "AQI 101-200 और अस्थमा: अपना राहत वाला inhaler साथ रखें, कसरत घर के अंदर करना बेहतर है, और "
            "ज़्यादा ट्रैफ़िक वाली सड़कों से बचें जहाँ NO2 अचानक बढ़ जाती है।",
        "CPCB-AQI-scale:201-300:any:outdoor_exercise:any":
            "AQI 201-300 (ख़राब): बाहर कसरत मत करें। बाहर जाना ज़रूरी हो तो कम समय के लिए और "
            "बिना ज़ोर लगाए जाएँ, और अच्छी तरह फ़िट होने वाला N95/FFP2 मास्क पहनें।",
        "WHO-AQG-2021:201-300:any:commute:any":
            "AQI 201-300 में आना-जाना: गाड़ी के शीशे बंद रखें और हवा को रीसर्कुलेशन पर रखें; "
            "दोपहिया पर N95 पहनें। मेट्रो में आमतौर पर सड़क के मुक़ाबले कम प्रदूषण लगता है।",
        "GINA-guidance:201-300:asthma:any:any":
            "AQI 201-300 और अस्थमा: खिड़कियाँ बंद करके घर के अंदर रहें, हो सके तो एयर "
            "प्यूरीफ़ायर चलाएँ, डॉक्टर के बताए अनुसार पहले से दवा लें, और अगर राहत वाले inhaler "
            "का इस्तेमाल बढ़ जाए तो डॉक्टर को दिखाएँ।",
        "AHA-airpollution:201-300:heart:any:any":
            "AQI 201-300 और दिल की बीमारी: बाहर मेहनत वाला काम न करें; बारीक कण थोड़े ही समय "
            "में सीने के दर्द (एनजाइना) और धड़कन की गड़बड़ी का ख़तरा बढ़ा देते हैं। सीने में "
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
            "तो N95 पहनें, और कोई तकलीफ़ बनी रहे तो अपने प्रसूति विशेषज्ञ (obstetrician) से बात करें।",
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
            "रीसर्कुलेशन पर चल रही बंद गाड़ी चुनें, क्योंकि सड़क किनारे PM2.5 और NO2 सबसे "
            "ज़्यादा होते हैं। जल्दबाज़ी न करें; प्रदूषित हवा में अचानक ज़ोर लगाना दिल पर भारी "
            "पड़ सकता है।",
        "GOLD-guidance:101-200:copd:any:any":
            "AQI 101-200 और COPD: बाहर कम समय बिताएँ और मेहनत वाले काम से बचें। ज़रूरी काम के "
            "लिए N95 पहनने पर विचार करें, PM10 से बचने के लिए खिड़कियाँ बंद रखें, और साँस फूलना "
            "या राहत वाले inhaler का इस्तेमाल बढ़ते ही तुरंत क़दम उठाएँ।",
        "ACOG-airquality:101-200:pregnancy:commute:any":
            "AQI 101-200 में गर्भावस्था के दौरान आना-जाना: PM2.5 कम अंदर जाए, इसके लिए मेट्रो "
            "या रीसर्कुलेशन पर चल रही बंद गाड़ी चुनें। दोपहिया पर हों या सड़क किनारे इंतज़ार "
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
            "से बाहर जाना ही पड़े तो N95 पहनें और कोई तकलीफ़ बनी रहे तो अपने प्रसूति विशेषज्ञ (obstetrician) को बताएँ।",
        "AHA-airpollution:201-300:heart:commute:any":
            "AQI 201-300 में दिल की बीमारी के साथ आना-जाना: दोपहिया और खुले ऑटो से बचें, वहाँ "
            "PM2.5 बहुत बढ़ जाता है; रीसर्कुलेशन पर चल रही बंद गाड़ी या मेट्रो लें, और N95 "
            "पहने रहें। सीने में दर्द या धड़कन तेज़ होने को आपात स्थिति मानें।",
        "WHO-AQG-2021:201-300:any:commute:senior":
            "AQI 201-300 में बुज़ुर्गों का आना-जाना: ग़ैर-ज़रूरी यात्रा टाल दें। जाना ही पड़े "
            "तो मेट्रो या रीसर्कुलेशन पर चल रही बंद गाड़ी लें, N95 पहनें, और सड़क किनारे "
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
            "बताई दवाइयाँ (जैसे नाइट्रेट) पास रखें, और सीने में दर्द या साँस फूलने को आपात "
            "स्थिति मानें।",
        # The rows added when persona filtering replaced persona scoring. Same
        # rule as above: identical force in both languages, nothing softened.
        "CPCB-AQI-scale:101-200:any:any:any":
            "AQI 101-200 (मध्यम): ज़्यादातर सेहतमंद लोगों पर असर नहीं पड़ता, पर इस स्तर पर "
            "अस्थमा जैसी फेफड़ों की बीमारी वालों को साँस लेने में तकलीफ़ होती है, और दिल की "
            "बीमारी वालों, बच्चों तथा बुज़ुर्गों को बेचैनी होती है। आप इनमें से किसी समूह में "
            "हैं तो बाहर कम समय बिताएँ और बिना जल्दबाज़ी के काम करें।",
        "CPCB-AQI-scale:201-300:any:any:any":
            "AQI 201-300 (ख़राब): ज़्यादा देर इस हवा में रहने पर ज़्यादातर लोगों को साँस लेने "
            "में तकलीफ़ होती है, और दिल की बीमारी वालों को बेचैनी होती है। बाहर उतना ही समय "
            "बिताएँ जितना ज़रूरी हो, खिड़कियाँ बंद रखें, और लंबे समय बाहर रहना पड़े तो अच्छी "
            "तरह फ़िट होने वाला N95 पहनें।",
        "GINA-guidance:301-999:asthma:any:any":
            "AQI 300 से ऊपर और अस्थमा: खिड़कियाँ बंद करके, फ़िल्टर की हुई हवा में घर के अंदर "
            "रहें और बाहर की सारी गतिविधि रद्द कर दें। रोज़ चलने वाली (controller) दवा लेते "
            "रहें, राहत वाला inhaler साथ रखें, और डॉक्टर की लिखी हुई हिदायतें मानें। राहत "
            "वाले inhaler की ज़रूरत लगातार बढ़ती जाए, उससे आराम न मिले, या साँस इतनी फूले कि "
            "पूरा वाक्य न बोल पाएँ, तो तुरंत डॉक्टर के पास जाएँ।",
        "GOLD-guidance:401-999:copd:any:any":
            "AQI 400 से ऊपर और COPD: इतनी ख़राब हवा से बीमारी अक्सर बिगड़ जाती है। बाहर "
            "बिल्कुल न निकलें, जिस कमरे में सबसे ज़्यादा रहते हैं वहाँ हवा साफ़ रखें, "
            "आपातकालीन दवा और डॉक्टर की लिखी हुई हिदायतें पास रखें, और ऑक्सीमीटर हो तो SpO2 "
            "देखते रहें। "
            "आराम करते हुए साँस फूलना, बलगम के रंग या मात्रा में बदलाव, या उलझन और नींद जैसी "
            "सुस्ती दिखे तो उसे आपात स्थिति मानकर तुरंत डॉक्टर के पास जाएँ।",
        "ACOG-airquality:401-999:pregnancy:any:any":
            "AQI 400 से ऊपर और गर्भावस्था: बाहर की हवा से पूरी तरह बचें और घर के अंदर हवा "
            "फ़िल्टर लगातार चलाएँ; PM2.5 का असर बच्चे के कम वज़न और समय से पहले जन्म से जुड़ा "
            "है। जो सफ़र टाला न जा सके उसके लिए अच्छी तरह फ़िट होने वाला N95 पहनें। आराम करते "
            "हुए साँस फूलना, सीने में दर्द, या बच्चे की हलचल में कोई बदलाव लगे तो उसी दिन अपने "
            "प्रसूति विशेषज्ञ (obstetrician) से संपर्क करें।",
        "AHA-airpollution:301-999:heart:any:any":
            "AQI 300 से ऊपर और दिल की बीमारी: इस स्तर पर बारीक कण थोड़े ही समय में दिल का "
            "दौरा, धड़कन की गड़बड़ी और स्ट्रोक का ख़तरा बढ़ा देते हैं। साफ़ की हुई हवा में घर "
            "के अंदर रहें, किसी तरह की मेहनत न करें, और डॉक्टर की बताई दवाइयाँ पास रखें। सीने "
            "में दर्द, धड़कन तेज़ होना, अचानक साँस फूलना या शरीर के एक तरफ़ कमज़ोरी को आपात "
            "स्थिति मानें और तुरंत मदद बुलाएँ।",
        "WHO-children-air:401-999:any:any:child":
            "AQI 400 से ऊपर और बच्चे: बच्चे बड़ों से तेज़ साँस लेते हैं और उनके फेफड़े अभी बन "
            "रहे होते हैं, इसलिए इतनी ख़राब हवा उन पर ज़्यादा असर करती है। उन्हें खिड़कियाँ बंद "
            "करके और प्यूरीफ़ायर चलाकर घर के अंदर रखें, बाहर खेलना और खेलकूद पूरी तरह बंद कर "
            "दें, और स्कूल से कहें कि बाहर की कक्षाएँ हटा दें या बंद रखें। घरघराहट, तेज़ या "
            "मुश्किल से चलती साँस, या बच्चा इतना हाँफ रहा हो कि खेल या दूध न ले पाए, तो डॉक्टर "
            "को दिखाएँ।",
        "AHA-airpollution:101-200:heart:any:any":
            "AQI 101-200 और दिल की बीमारी: इस स्तर पर भी बेचैनी हो सकती है, इसलिए बाहर लंबी या "
            "ज़्यादा मेहनत वाली गतिविधि कम कर दें और व्यस्त सड़कों से दूर रहें जहाँ PM2.5 और "
            "NO2 सबसे ज़्यादा होते हैं। सीने में जकड़न, धड़कन तेज़ होना या असामान्य रूप से साँस "
            "फूलने पर रुककर आराम करें, और आराम न मिले तो डॉक्टर को दिखाएँ।",
        "ACOG-airquality:151-200:pregnancy:any:any":
            "AQI 151-200 और गर्भावस्था: बाहर कम समय बिताएँ और बिना जल्दबाज़ी के चलें, तथा "
            "मुख्य सड़कों के बजाय पार्क और शांत गलियाँ चुनें। हो सके तो घर के अंदर हवा फ़िल्टर "
            "करें, क्योंकि पूरी गर्भावस्था में जुड़ता PM2.5 बच्चे के कम वज़न से जुड़ा है। साँस "
            "फूलने या लगातार खाँसी की बात अपने प्रसूति विशेषज्ञ (obstetrician) को बताएँ।",
    },
}
