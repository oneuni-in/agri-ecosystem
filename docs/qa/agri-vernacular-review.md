# A-U2 vernacular review sheet (AG-A24)

Generated from `backend/core/modules/market_data/weather.py` by
`scripts/gen_vernacular_review.py`. Regenerate rather than hand-edit, so it
cannot drift from the code it is reviewing.

**What needs a native speaker, and why these first.** A-U2 authored roughly 57
Tamil and 57 Hindi strings, and they are not equal risk:

- The pairs below **carry ADVICE** — when to spray, when to hold off urea, when
  to irrigate, what disease to scout for, and severe-weather warnings. A wrong
  nuance changes what a farmer *does*. These are worth a careful read.
- The other ~38 are weather-condition labels and weekday abbreviations in
  `wmo.py` ("Overcast", "Light drizzle", "Mon"). An awkward word there is
  cosmetic. Review them second, or not at all.

`{day.ta}`, `{end.ta}`, `{wet.ta}` and `{hours}` are placeholders filled at
render time with a weekday abbreviation or a number.

The English column is the source of truth: the Tamil and Hindi should say the
same thing to a farmer, not match word for word.

## Advice strings — please check

| # | English | Tamil | Hindi | OK? |
|---|---|---|---|---|
| 1 | Spray window advisory | தெளிப்பு நேர அறிவுரை | छिड़काव सलाह | |
| 2 | Tip of the day | இன்றைய குறிப்பு | आज का सुझाव | |
| 3 | next {hours} hrs | அடுத்த {hours} மணி நேரம் | अगले {hours} घंटे | |
| 4 | Good spraying conditions across the forecast — no wash-off rain expected. | முன்னறிவிப்பு முழுவதும் தெளிக்க ஏற்ற நிலை — மருந்து அடித்துச் செல்லும் மழை இல்லை. | पूरे पूर्वानुमान में छिड़काव अनुकूल — बहा देने वाली बारिश नहीं। | |
| 5 | Good spraying conditions till {end.en}. Avoid from {wet.en} — rain likely to wash off application. | {end.ta} வரை தெளிக்கலாம். {wet.ta} முதல் தவிர்க்கவும் — மழை மருந்தை அடித்துச் செல்லும். | {end.hi} तक छिड़काव ठीक। {wet.hi} से बचें — बारिश दवा बहा देगी। | |
| 6 | Rain likely across the whole forecast — hold off spraying; application now is likely to wash off. | முழு வானிலை முன்னறிவிப்பிலும் மழை — இப்போது தெளிக்க வேண்டாம், மருந்து அடித்துச் செல்லப்படும். | पूरे पूर्वानुमान में बारिश — अभी छिड़काव न करें, दवा बह जाएगी। | |
| 7 | Rain likely today — postpone spraying. Conditions look suitable again from {day.en}. | இன்று மழை வாய்ப்பு — தெளிப்பதை தள்ளிப்போடுங்கள். {day.ta} முதல் மீண்டும் ஏற்றது. | आज बारिश संभव — छिड़काव टालें। {day.hi} से दोबारा उपयुक्त। | |
| 8 | Heavy rain expected {day.en} — postpone urea top-dressing. Nitrogen applied before heavy rain is lost to runoff. | {day.ta} கனமழை — யூரியா இடுவதை தள்ளிப்போடுங்கள். கனமழைக்கு முன் இட்டால் நைட்ரஜன் வீணாகும். | {day.hi} भारी बारिश — यूरिया टॉप-ड्रेसिंग टालें। भारी बारिश से पहले डाला नाइट्रोजन बह जाता है। | |
| 9 | No rain in the next five days — plan irrigation and mulch to hold soil moisture. | அடுத்த ஐந்து நாட்களில் மழை இல்லை — பாசனம் திட்டமிடுங்கள், மண் ஈரப்பதம் காக்க மூடாக்கு இடுங்கள். | अगले पांच दिन बारिश नहीं — सिंचाई की योजना बनाएं और नमी बचाने को मल्च करें। | |
| 10 | High humidity with wet spells — scout for fungal leaf spot and keep field drainage clear. | அதிக ஈரப்பதமும் மழையும் — பூஞ்சை இலைப்புள்ளி நோயை கண்காணியுங்கள், வடிகால் தடையின்றி வைக்கவும். | अधिक नमी और बारिश — फफूंदी पत्ती धब्बा रोग की जांच करें, जल निकासी साफ़ रखें। | |
| 11 | Extremely heavy rain warning | மிகக் கடும் மழை எச்சரிக்கை | अत्यधिक भारी बारिश की चेतावनी | |
| 12 | Gale-force wind warning | பலத்த காற்று எச்சரிக்கை | तेज़ आंधी की चेतावनी | |
| 13 | Severe thunderstorm with hail | ஆலங்கட்டியுடன் கடும் இடிமழை | ओलों के साथ भीषण तूफ़ान | |
| 14 | Very heavy rain warning | மிகக் கனமழை எச்சரிக்கை | अति भारी बारिश की चेतावनी | |
| 15 | Heavy rain warning | கனமழை எச்சரிக்கை | भारी बारिश की चेतावनी | |

## Recording the outcome

Tick the OK column, or replace the cell with the wording you want. Anything
changed here has to go back into `weather.py` — this file is a review surface,
not the source.

Least certain, flagged by the author:

- **தெளிப்பு** for spraying — correct for pesticide application, but confirm it is
  what a farmer in the Coimbatore belt would say rather than a textbook term.
- **மூடாக்கு** (mulch) and **பூஞ்சை இலைப்புள்ளி** (fungal leaf spot) are agronomic
  terms; a field-accurate synonym may read better.
- The Hindi severe-weather headlines deliberately mirror IMD's own phrasing
  (**भारी बारिश की चेतावनी**). Keep that alignment if you reword them — people
  recognise the official form.
- Numbers, units and crop names stay in the English column's form on purpose;
  the UI formats them.
