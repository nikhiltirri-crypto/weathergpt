from typing import Dict, Any, List

class AdvisoryService:
    @staticmethod
    def generate_advisories(current_weather: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
        temp = current_weather.get("temperature", 28.0)
        humidity = current_weather.get("humidity", 60)
        wind_speed = current_weather.get("wind_speed", 10.0)
        rain_prob = current_weather.get("rain_probability", 20)
        uv = current_weather.get("uv_index", 5.0)
        weather_code = current_weather.get("weather_code", 0)
        precip = float(current_weather.get("precipitation", 0.0) or 0.0)
        cape = float(current_weather.get("cape", 0.0) or 0.0)

        # Strict meteorological condition: precip > 1.0mm OR WMO code 80-99
        is_active_rain_or_storm = (precip > 1.0) or (80 <= weather_code <= 99)

        # 1. Agriculture / Farming Evaluation
        agri_status = "good"
        agri_recs = []
        if is_active_rain_or_storm and (weather_code in [65, 82, 95, 96, 99] or precip > 1.0):
            agri_status = "warning"
            agri_msg_en = "Heavy rain/showers expected. Suspend pesticide spraying and postpone field harvesting."
            agri_recs.append("Drain excess water from low-lying crop beds to prevent root rot.")
            agri_recs.append("Avoid nitrogenous fertilizer top-dressing right before heavy downpours.")
            agri_recs.append("Secure harvested produce in moisture-proof godowns or elevated tarpaulins.")
        elif not is_active_rain_or_storm and (cape >= 1000.0 or humidity >= 75):
            agri_status = "caution"
            agri_msg_en = "Hot/Humid with convective potential. Elevated humidity and thermal energy; no active storm in progress."
            agri_recs.append("Keep crop drainage channels clear in case late-day convective showers develop.")
            agri_recs.append("Maintain good livestock ventilation in warm humid conditions.")
        elif rain_prob >= 35:
            agri_status = "caution"
            agri_msg_en = "Moderate probability of rain. Suitable for natural soil moistening; reduce artificial irrigation."
            agri_recs.append("Hold planned irrigation for 24 hours to monitor rainfall accumulation.")
            agri_recs.append("Foliar sprays can be done if rain is delayed past 4 hours.")
        elif temp >= 38:
            agri_status = "danger"
            agri_msg_en = "Extreme heat condition. High crop evapotranspiration and livestock thermal distress risk."
            agri_recs.append("Apply light, frequent evening irrigation or drip watering to maintain root-zone moisture.")
            agri_recs.append("Ensure shaded shelters, cool water, and electrolytes for cattle and poultry.")
            agri_recs.append("Provide straw mulching around vegetable beds to curb soil moisture evaporation.")
        else:
            agri_status = "good"
            agri_msg_en = "Favorable agricultural conditions. Ideal window for sowing, weeding, and farm operations."
            agri_recs.append("Good time for routine irrigation and scheduled agronomic treatments.")
            agri_recs.append("Normal harvesting and grain sun-drying can proceed safely.")

        if wind_speed > 25:
            agri_recs.append(f"Wind speed is elevated ({wind_speed} km/h). Provide staking for banana, papaya, and young saplings.")

        # 2. Travel & Logistics Evaluation
        travel_status = "good"
        travel_recs = []
        if is_active_rain_or_storm and weather_code in [95, 96, 99]:
            travel_status = "danger"
            travel_msg_en = "Thunderstorm / lightning hazard. Limit non-essential highway travel and avoid open high-elevation stretches."
            travel_recs.append("Do not park vehicles under old trees, weak hoardings, or electric poles.")
            travel_recs.append("Expect airline and train speed restrictions in thunderstorm corridors.")
        elif is_active_rain_or_storm and (precip > 1.0 or weather_code in [61, 62, 63, 65, 80, 81, 82]):
            travel_status = "warning"
            travel_msg_en = "Wet roads and reduced visibility expected. Allow extra transit time."
            travel_recs.append("Drive with low-beam headlights on wet stretches; increase braking distance.")
            travel_recs.append("Check local drainage conditions before entering underpasses or subways.")
        elif not is_active_rain_or_storm and (cape >= 1000.0 or humidity >= 75):
            travel_status = "good"
            travel_msg_en = "Hot/Humid with convective potential. No active storm occurring; roads are clear."
            travel_recs.append("Ensure in-car AC/ventilation is working well given high humidity.")
        elif wind_speed >= 35:
            travel_status = "warning"
            travel_msg_en = "Strong crosswinds detected. High-sided vehicles and two-wheelers must exercise caution on flyovers and coastal roads."
            travel_recs.append("Reduce speed on open bridges and expressways.")
        else:
            travel_status = "good"
            travel_msg_en = "Clear travel conditions across road and rail corridors. Normal transit expected."
            travel_recs.append("Ideal conditions for inter-city travel and outdoor commuting.")

        # 3. General Public & Health Evaluation
        public_status = "good"
        public_recs = []
        if rain_prob >= 40:
            public_recs.append("Carry an umbrella or rain poncho when stepping out.")
        if temp >= 37:
            public_status = "warning"
            public_msg_en = f"High thermal index ({temp}°C). Heat stress precautions recommended."
            public_recs.append("Drink plenty of water, tender coconut, or ORS; do not wait until thirsty.")
            public_recs.append("Avoid prolonged direct sun exposure between 12:00 PM and 3:30 PM.")
            public_recs.append("Wear loose, light-colored cotton clothing and wide-brimmed hats.")
        elif uv >= 7:
            public_status = "caution"
            public_msg_en = f"Very high UV index ({uv}). Sun protection is advised."
            public_recs.append("Apply SPF 30+ sunscreen if outdoors for extended periods.")
            public_recs.append("Wear UV-protective sunglasses.")
        elif rain_prob >= 50:
            public_status = "caution"
            public_msg_en = f"Rain likely ({rain_prob}% probability). Keep weather gear handy."
            public_recs.append("Carry an umbrella; wear waterproof footwear.")
            public_recs.append("Keep phone and electronics in waterproof pouches.")
        elif not is_active_rain_or_storm and (cape >= 1000.0 or humidity >= 75):
            public_status = "caution"
            public_msg_en = "Hot/Humid with convective potential. Elevated humidity impedes sweat cooling; ensure continuous hydration."
            public_recs.append("Drink water regularly throughout the day.")
            public_recs.append("Wear loose breathable fabrics and stay in well-ventilated areas.")
        else:
            public_status = "good"
            public_msg_en = "Pleasant ambient weather. Comfortable for outdoor physical activities."
            public_recs.append("Great weather for morning jogs, walks, and outdoor family gatherings.")

        # Multilingual Translation Layer for Indian Languages
        translations = {
            "hi": {
                "disclaimer": "मौसमजीपीटी द्वारा उत्पन्न सूचनात्मक निर्णय सहायता; यह आधिकारिक आपातकालीन निर्देशों का विकल्प नहीं है।",
                "agri_title": "कृषि एवं किसान सलाह",
                "travel_title": "यात्रा एवं परिवहन परामर्श",
                "public_title": "सार्वजनिक स्वास्थ्य एवं दैनिक जीवन",
                "agri_msg": {
                    "good": "कृषि के लिए अनुकूल स्थिति। बुवाई, निराई और सामान्य कृषि कार्यों के लिए उत्तम समय।",
                    "caution": "मध्यम बारिश की संभावना। प्राकृतिक नमी उपलब्ध रहेगी; सिंचाई की आवश्यकता कम करें।",
                    "warning": "भारी वर्षा का अनुमान। कीटनाशक छिड़काव स्थगित करें और कटी फसल को सुरक्षित रखें।",
                    "danger": "अत्यधिक गर्मी का प्रभाव। फसलों में नमी की कमी व पशुओं के लिए विशेष सावधानी बरतें।"
                },
                "travel_msg": {
                    "good": "सड़क और रेल यात्रा के लिए मौसम बिल्कुल साफ और अनुकूल है।",
                    "warning": "गीली सड़कें व दृश्यता में कमी। यात्रा में अतिरिक्त समय लेकर चलें और गति नियंत्रित रखें।",
                    "danger": "आंधी-तूफान व बिजली गिरने का खतरा। अनावश्यक यात्रा से बचें और सुरक्षित स्थानों पर रहें।"
                },
                "public_msg": {
                    "good": "सुहावना मौसम। बाहरी गतिविधियों के लिए उपयुक्त समय।",
                    "caution": "बारिश या तेज धूप की संभावना। छतरी साथ रखें और सावधानी बरतें।",
                    "warning": "गर्मी व उच्च तापमान का असर। पर्याप्त पानी पिएं और दोपहर की धूप से बचें।"
                }
            },
            "te": {
                "disclaimer": "వెదర్ జీపీటీ అందించిన సమాచార నిర్ణయ మద్దతు; ఇది అధికారిక అత్యవసర ఆదేశాలకు ప్రత్యామ్నాయం కాదు.",
                "agri_title": "వ్యవసాయ & రైతు సలహా",
                "travel_title": "ప్రయాణ & లాజిస్టిక్స్ సూచనలు",
                "public_title": "ప్రజా ఆరోగ్యం & సాధారణ జీవితం",
                "agri_msg": {
                    "good": "వ్యవసాయ పనులకు అనుకూల వాతావరణం. విత్తనాలు వేయడం, కలుపు తీయడానికి సరైన సమయం.",
                    "caution": "వర్షం పడే అవకాశం ఉంది. సహజ తేమ లభిస్తుంది; అనవసర నీటిపారుదల తగ్గించండి.",
                    "warning": "భారీ వర్ష సూచన. పురుగుమందుల పిచికారీని వాయిదా వేయండి, పంటను రక్షించండి.",
                    "danger": "తీవ్రమైన ఎండ వేడిమి. పంటలకు డ్రిప్ నీరు అందించండి, పశువుల పట్ల జాగ్రత్త వహించండి."
                },
                "travel_msg": {
                    "good": "రహదారి మరియు ప్రయాణాలకు వాతావరణం అనుకూలంగా ఉంది.",
                    "warning": "వర్షం కారణంగా రోడ్లు జారే అవకాశం ఉంది. వాహనాల వేగాన్ని నియంత్రించండి.",
                    "danger": "ఉరుములు, మెరుపుల ప్రమాదం. అత్యవసరమైతే తప్ప ప్రయాణాలు వాయిదా వేయండి."
                },
                "public_msg": {
                    "good": "ఆహ్లాదకరమైన వాతావరణం. బహిరంగ పనులకు అనుకూలం.",
                    "caution": "వర్షం సూచన ఉంది. బయటకు వెళ్లేటప్పుడు గొడుగు తీసుకెళ్లండి.",
                    "warning": "తీవ్రమైన ఉష్ణోగ్రత. ఎక్కువ నీరు త్రాగండి, మధ్యాహ్నం ఎండలో తిరగవద్దు."
                }
            },
            "ta": {
                "disclaimer": "வெதர்ஜிபிடி தகவல் முடிவு ஆதரவு; இது அவசரகால அதிகாரப்பூர்வ உத்தரவுகளுக்கு மாற்றாகாது.",
                "agri_title": "விவசாயம் மற்றும் உழவர் ஆலோசனைகள்",
                "travel_title": "பயண மற்றும் போக்குவரத்து வழிகாட்டுதல்",
                "public_title": "பொது சுகாதாரம் மற்றும் தினசரி வாழ்வு",
                "agri_msg": {
                    "good": "விவசாய பணிகளுக்கு சாதகமான வானிலை. விதைப்பு மற்றும் அறுவடைக்கு உகந்த நேரம்.",
                    "caution": "மழைக்கு வாய்ப்பு உள்ளது. கூடுதல் நீர்ப்பாசனத்தை தவிர்க்கவும்.",
                    "warning": "கனமழை எச்சரிக்கை. பூச்சிக்கொல்லி தெளிப்பதை நிறுத்தி, விளைபொருட்களை பாதுகாக்கவும்.",
                    "danger": "அதிக வெப்பம். பயிர்களுக்கு மாலையில் நீர் பாய்ச்சவும், கால்நடைகளை நிழலில் வைக்கவும்."
                },
                "travel_msg": {
                    "good": "பயணம் செய்ய தெளிவான மற்றும் பாதுகாப்பான வானிலை நிலவுகிறது.",
                    "warning": "ஈரமான சாலைகள் மற்றும் குறைந்த பார்வை தூரம். எச்சரிக்கையுடன் வாகனத்தை இயக்கவும்.",
                    "danger": "இடி மின்னல் அபாயம். அத்தியாவசியமற்ற வெளிப்புற பயணங்களைத் தவிர்க்கவும்."
                },
                "public_msg": {
                    "good": "இதமான வானிலை. வெளிப்புற வேலைகளுக்கு சிறந்தது.",
                    "caution": "மழை வாய்ப்பு. வெளியே செல்லும்போது குடை எடுத்துச் செல்லுங்கள்.",
                    "warning": "அதிக வெப்பம். போதுமான அளவு தண்ணீர் குடிக்கவும், வெயிலில் செல்வதை தவிர்க்கவும்."
                }
            },
            "ml": {
                "disclaimer": "വെതർജിപിടി നൽകുന്ന വിവരങ്ങൾ; ഇത് ഔദ്യോഗിക അടിയന്തര നിർദ്ദേശങ്ങൾക്ക് പകരമല്ല.",
                "agri_title": "കാർഷിക & കർഷക ഉപദേശം",
                "travel_title": "യാത്രാ & ഗതാഗത മുന്നറിയിപ്പ്",
                "public_title": "പൊതുജനാരോഗ്യവും ദിനചര്യയും",
                "agri_msg": {
                    "good": "കൃഷിക്ക് അനുയോജ്യമായ കാലാവസ്ഥ. വിളവെടുപ്പിനും വിതയ്ക്കും ഉചിതമായ സമയം.",
                    "caution": "മഴയ്ക്ക് സാധ്യത. ആവശ്യമില്ലാത്ത ജലസേചനം ഒഴിവാക്കുക.",
                    "warning": "കനത്ത മഴ മുന്നറിയിപ്പ്. കീടനാശിനി തളിക്കുന്നത് മാറ്റിവെക്കുക, വിളകൾ സംരക്ഷിക്കുക.",
                    "danger": "കടുത്ത വേനൽച്ചൂട്. വിളകൾക്ക് ആവശ്യത്തിന് ഈർപ്പം ഉറപ്പാക്കുക, കന്നുകാലികളെ സംരക്ഷിക്കുക."
                },
                "travel_msg": {
                    "good": "യാത്രകൾക്ക് അനുയോജ്യമായ കാലാവസ്ഥ.",
                    "warning": "നനഞ്ഞ റോഡുകൾ. വാഹനം ഓടിക്കുമ്പോൾ ജാഗ്രത പാലിക്കുക.",
                    "danger": "ഇടിമിന്നൽ ജാഗ്രത. അത്യാവശ്യമല്ലാത്ത യാത്രകൾ ഒഴിവാക്കുക."
                },
                "public_msg": {
                    "good": "സുഖകരമായ കാലാവസ്ഥ. പ്രഭാത നടത്തത്തിനും പുറത്തിറങ്ങാനും അനുയോജ്യം.",
                    "caution": "മഴ പെയ്യാൻ സാധ്യത. കുട കയ്യിൽ കരുതുക.",
                    "warning": "കൂടിയ താപനില. ധാരാളം വെള്ളം കുടിക്കുക, കടുത്ത വെയിൽ ഒഴിവാക്കുക."
                }
            }
        }

        # Apply translations if available
        t = translations.get(lang)
        if t:
            disclaimer = t["disclaimer"]
            agri_title = t["agri_title"]
            travel_title = t["travel_title"]
            public_title = t["public_title"]
            agri_primary = t["agri_msg"].get(agri_status, agri_msg_en)
            travel_primary = t["travel_msg"].get(travel_status, travel_msg_en)
            public_primary = t["public_msg"].get(public_status, public_msg_en)
        else:
            disclaimer = "Informational decision support generated by WeatherGPT AI; not a substitute for official emergency authority directives."
            agri_title = "Agriculture & Farming Advisory"
            travel_title = "Travel & Logistics Advisory"
            public_title = "General Public & Health Advisory"
            agri_primary = agri_msg_en
            travel_primary = travel_msg_en
            public_primary = public_msg_en

        return {
            "city": current_weather.get("city", "Visakhapatnam"),
            "language": lang,
            "disclaimer": disclaimer,
            "agriculture": {
                "title": agri_title,
                "icon": "Sprout",
                "status": agri_status,
                "primary_message": agri_primary,
                "recommendations": agri_recs
            },
            "travel": {
                "title": travel_title,
                "icon": "Car",
                "status": travel_status,
                "primary_message": travel_primary,
                "recommendations": travel_recs
            },
            "general_public": {
                "title": public_title,
                "icon": "Umbrella",
                "status": public_status,
                "primary_message": public_primary,
                "recommendations": public_recs
            },
            "is_demo": current_weather.get("is_demo", False)
        }
