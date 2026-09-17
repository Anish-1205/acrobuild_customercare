import type { VoiceLanguageCode } from "./voiceLanguage";

export type ChatLanguage =
  | "en" | "hi" | "hi-deva" | "te" | "te-telu" | "ta" | "kn" | "ml" | "mr" | "bn" | "gu" | "pa";

// Mirrors services/reply_language.py (ROMANIZED_LEXICONS). Keep the two in sync.
const ROMANIZED_TERMS: Array<[ChatLanguage, Set<string>]> = [
  ["hi", new Set(`hai hain kya kyun kaise kaisa kaisi kahan kab kaun kaunsa konsa konse kaunse mujhe mera
    meri mere aap aapka aapke aapko apke tum tumhara nahi nahin haan chahiye batao bataiye dikhao dikhaiye
    kijiye kitna kitne kitni ghar bhai accha acha theek thik samajh boliye mein raha rahi rahe hoga sakte
    sakta wala wali wale paas liye abhi kuch bahut kripya`.split(/\s+/))],
  ["te", new Set(`enti emiti emi ela elaa unnava unnaru unnayi unnaya naku naaku meeku miku kavali kaavali
    cheppu cheppandi avunu ledu levu enduku eppudu ekkada bagunnara bagunnava namaskaram cheddam chedham
    chedama cheyandi chupinchu chupinchandi manam entha illu evi kosam vaccha vacha vachu vacchu telusu
    telidu peru nenu nuvvu meeru ayindi undi ivvandi matladu matladandi evaru nee em chestunnav chestunav`.split(/\s+/))],
  ["ta", new Set(`enna yenna epdi eppadi enga engae yaar yaaru evvalavu evlo sollu sollunga irukku irukka
    iruku irukkinga venum vendum panren pandre panra panringa pannunga naan neenga unga ungal enakku
    ungalukku illai aama vanakkam romba nalla theriyuma theriyum pesu pesunga peyar kaatu kaatunga veedu`.split(/\s+/))],
  ["kn", new Set(`enu yenu hege hegiddira hegiddiya elli yelli beku bekagide helu heli nimma nimge nanna
    nange naanu neevu ide idhe yaava yavdu thorisi torisi eshtu estu maadi banni gottilla gottu hesaru
    chennagi namaskara`.split(/\s+/))],
  ["ml", new Set(`enthu enthanu evide engane venam vendi parayu parayoo ningal ningalude ente enikku kanikku
    ethra sugamano sukhamano alle aano aanu cheyyam pinne`.split(/\s+/))],
  ["mr", new Set(`aahe ahe aahet kay kasa kashi kase kuthe kuthla kuthle konte mala tumhi tumhala amhi pahije
    madhe madhye bola sanga dakhva dakhava kiti nako kaay jhala zala`.split(/\s+/))],
  ["bn", new Set(`achhe acho achen ami amar tumi tomar apni apnar koto kothay kothae dekhao bolo bolun lagbe
    nei kemon bhalo korbo koro korun dhonnobad`.split(/\s+/))],
  ["gu", new Set(`che chhe cho shu shun tamne tamaru joie joiye kem batavo ketla ketlu nathi saru majama
    avjo`.split(/\s+/))],
  ["pa", new Set(`tusi tuhanu sanu chahida kiddan kithe dasso kinne kinna haige naal vich`.split(/\s+/))]
];

const LANGUAGE_NAMES: Record<string, ChatLanguage> = {
  english: "en", hindi: "hi", hinglish: "hi", telugu: "te", tenglish: "te", tamil: "ta", tanglish: "ta",
  kannada: "kn", malayalam: "ml", marathi: "mr", bengali: "bn", bangla: "bn", gujarati: "gu", punjabi: "pa"
};

// Devanagari words distinctive of Marathi (not shared with standard Hindi), so a
// native-script Marathi message isn't misread as Hindi. Mirrors reply_language.py.
const MARATHI_DEVANAGARI_MARKERS = new Set(
  `\u0906\u0939\u0947 \u0906\u0939\u0947\u0924 \u0905\u0939\u0947 \u0906\u0939\u093E\u0924 \u0915\u0938\u093E \u0915\u0936\u0940 \u0915\u0938\u0947 \u0915\u0941\u0920\u0947 \u0915\u0941\u0920\u0932\u093E \u0915\u0941\u0920\u0932\u0940 \u0915\u0941\u0920\u0932\u0947 \u0915\u094B\u0923\u0924\u093E \u0915\u094B\u0923\u0924\u0940 \u0915\u094B\u0923\u0924\u0947
   \u092E\u0932\u093E \u0924\u0941\u092E\u094D\u0939\u0940 \u0924\u0941\u092E\u094D\u0939\u093E\u0932\u093E \u0906\u092E\u094D\u0939\u093E\u0932\u093E \u0906\u092E\u094D\u0939\u0940 \u092E\u093E\u091D\u094D\u092F\u093E \u0924\u0941\u092E\u091A\u094D\u092F\u093E \u092A\u093E\u0939\u093F\u091C\u0947 \u092E\u0927\u094D\u092F\u0947 \u092C\u094B\u0932\u093E \u0938\u093E\u0902\u0917\u093E
   \u0926\u093E\u0916\u0935\u093E \u0915\u093F\u0924\u0940 \u0928\u0915\u094B \u091D\u093E\u0932\u093E \u091D\u093E\u0932\u0940 \u091D\u093E\u0932\u0902 \u092E\u0930\u093E\u0920\u0940 \u092E\u093E\u0932\u092E\u0924\u094D\u0924\u093E \u0928\u093E\u0939\u0940`.split(/\s+/)
);

const SCRIPT_LANGUAGES: Array<[RegExp, ChatLanguage]> = [
  [/[\u0980-\u09FF]/, "bn"],
  [/[\u0900-\u097F]/, "hi-deva"],
  [/[\u0A00-\u0A7F]/, "pa"],
  [/[\u0A80-\u0AFF]/, "gu"],
  [/[\u0B80-\u0BFF]/, "ta"],
  [/[\u0C00-\u0C7F]/, "te-telu"],
  [/[\u0C80-\u0CFF]/, "kn"],
  [/[\u0D00-\u0D7F]/, "ml"]
];

const VOICE_CHAT_LANGUAGES: Partial<Record<VoiceLanguageCode, ChatLanguage>> = {
  "hi-IN": "hi-deva", "te-IN": "te-telu", "ta-IN": "ta", "kn-IN": "kn", "ml-IN": "ml",
  "mr-IN": "mr", "bn-IN": "bn", "gu-IN": "gu", "pa-IN": "pa"
};

const ENGLISH_TERMS = new Set([
  "what", "which", "show", "is", "are", "do", "you", "have", "the", "please", "how", "can",
  "want", "need", "list", "tell", "me", "my", "browse"
]);

export function detectChatLanguage(
  text: string,
  selectedLanguage: VoiceLanguageCode,
  previous: ChatLanguage
): ChatLanguage {
  const script = SCRIPT_LANGUAGES.find(([pattern]) => pattern.test(text));
  if (script) {
    if (script[1] === "hi-deva" && (text.match(/[ऀ-ॿ]+/g) ?? []).some((word) => MARATHI_DEVANAGARI_MARKERS.has(word))) {
      return "mr";
    }
    return script[1];
  }
  const voiceLanguage = VOICE_CHAT_LANGUAGES[selectedLanguage];
  if (voiceLanguage) return voiceLanguage;

  const words = text.toLowerCase().match(/[a-z]+/g) ?? [];
  const named = [...new Set(words.map((word) => LANGUAGE_NAMES[word]).filter(Boolean))];
  if (named.length === 1) return named[0];

  let best: ChatLanguage | null = null;
  let bestScore = 0;
  for (const [language, terms] of ROMANIZED_TERMS) {
    const score = words.filter((word) => terms.has(word)).length;
    if (score > bestScore) {
      best = language;
      bestScore = score;
    }
  }
  if (best) return best;
  if (words.some((word) => ENGLISH_TERMS.has(word))) return "en";
  return previous;
}

const REPLY_LANGUAGE_CODES: Record<string, ChatLanguage> = {
  english: "en", tamil: "ta", kannada: "kn", malayalam: "ml", marathi: "mr", bengali: "bn",
  gujarati: "gu", punjabi: "pa"
};

/** Maps the backend's detected reply language onto the guided-flow text table. */
export function chatLanguageFromReply(
  language: string | undefined,
  script: string | undefined,
  previous: ChatLanguage
): ChatLanguage {
  const name = (language ?? "").trim().toLowerCase();
  if (name === "hindi") return script === "native" ? "hi-deva" : "hi";
  if (name === "telugu") return script === "native" ? "te-telu" : "te";
  return REPLY_LANGUAGE_CODES[name] ?? previous;
}

export function isProjectBrowseRequest(value: string, knownProjectNames: string[] = []) {
  const normalizedValue = value.trim().toLowerCase().replace(/[.!?]+$/g, "").trim();
  if (/^(projects?|प्रोजेक्ट्?स?|ప్రాజెక్ట్‌?లు?)$/.test(normalizedValue)) return true;
  if (/\b(?:browse|show|list)(?: me)?(?: all)?(?: the)? projects\b/.test(normalizedValue)) return true;
  if (knownProjectNames.some((name) => name && normalizedValue.includes(name.trim().toLowerCase()))) return false;

  const mentionsInventory =
    /\b(?:projects?|flats?|homes?|apartments?|properties|property|ghar|makaan|illu|veedu)\b|प्रोजेक्ट|फ्लैट|घर|मकान|ప్రాజెక్ట్|ఫ్లాట్|ఇళ్ళు|ఇల్లు/.test(normalizedValue);
  const asksToList =
    /\b(?:available|availability|which|what|show|list|browse|konse|kaunse|kaun|kya|dikhao|dikhaiye|batao|bataiye|enti|emi|evi|unnayi|unnaya|chupinchu|chupinchandi|enna|enga|irukku|kaatu|kaatunga|yaava|ide|thorisi|ethu|kanikku|kuthle|konte|aahet|dakhva|kon|achhe|dekhao|kaya|che|batavo|kehde|dasso)\b|कौन|क्या|दिखा|बता|उपलब्ध|ఏవి|ఏమి|ఉన్నాయి|చూపించ/.test(normalizedValue);
  // A trailing "in/near/at/mein <place>" is treated as a scope, not a disqualifier
  // — see extractLocationHint, which narrows the button list to that place.
  const isSpecific =
    /\d|bhk|\brk\b|price|cost|rate|budget|floor|wing|shop|sq|cheap|expensive|location|कीमत|दाम|में |ధర|లో /.test(normalizedValue);
  return mentionsInventory && asksToList && !isSpecific;
}

const PREPOSITION_LOCATION_RE = /\b(?:in|near|around|at)\s+([a-z][a-z\s]{1,30}?)(?=[.?!]|$)/;
// Indian languages put the place before a postposition: "thane lo", "pune mein", "kalyan madhe".
const POSTPOSITION_LOCATION_RE = /\b([a-z]{3,})\s+(?:lo|la|le|alli|madhe|madhye|mein|ma|vich|il|ile|daggara|pakkathula|javal)\b/g;
const NOT_A_PLACE = new Set(
  `flats flat projects project homes home properties property apartments apartment ghar illu veedu
   english hindi telugu tamil kannada malayalam marathi bengali bangla gujarati punjabi aapke hamare
   yahan wahan ikkada akkada ekkada inga anga ivide`.split(/\s+/)
);

function titleCase(value: string) {
  return value.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function extractLocationHint(value: string): string | null {
  const normalizedValue = value.trim().toLowerCase().replace(/[.!?]+$/g, "").trim();
  const preposition = PREPOSITION_LOCATION_RE.exec(normalizedValue);
  if (preposition?.[1].trim()) return titleCase(preposition[1].trim());
  for (const match of normalizedValue.matchAll(POSTPOSITION_LOCATION_RE)) {
    if (!NOT_A_PLACE.has(match[1])) return titleCase(match[1]);
  }
  return null;
}

type FlowText = {
  bookVisit: string;
  browseAll: string;
  canBookVisit: string;
  carpetArea: string;
  chooseFlat: (floor: number) => string;
  chooseFloor: (wing: string) => string;
  chooseProject: (count: number) => string;
  chooseProjectInLocation: (count: number, location: string) => string;
  chooseWing: (project: string) => string;
  flat: (unit: string | number) => string;
  floor: (floor: number) => string;
  livePrice: string;
  noFlatsInWing: (wing: string) => string;
  noFlatsOnFloor: (floor: number) => string;
  noProjects: string;
  noProjectsInLocation: (location: string) => string;
  noWings: (project: string) => string;
  priceNotListed: string;
  saleableArea: string;
  stepFailed: string;
};

export const FLOW_TEXT: Record<ChatLanguage, FlowText> = {
  en: {
    bookVisit: "Book a site visit",
    browseAll: "Browse all projects",
    canBookVisit: "You can now request a site visit for this flat.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Choose an available flat on floor ${floor}.`,
    chooseFloor: (wing) => `Choose a floor in ${wing}.`,
    chooseProject: (count) => `Choose a project to explore. ${count} live project${count === 1 ? " is" : "s are"} available.`,
    chooseProjectInLocation: (count, location) => `Here are the flats available in and around ${location}. Choose a project to explore. ${count} live project${count === 1 ? " is" : "s are"} available.`,
    chooseWing: (project) => `Choose a wing in ${project}.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing} does not currently have available flats. You can still request a site visit.`,
    noFlatsOnFloor: (floor) => `No available flats are currently listed on floor ${floor}.`,
    noProjects: "No live projects are currently available.",
    noProjectsInLocation: (location) => `No live projects are currently available in and around ${location}.`,
    noWings: (project) => `${project} does not currently have any wings available.`,
    priceNotListed: "Price not listed",
    saleableArea: "Saleable area",
    stepFailed: "I could not load that live property step. Please try again."
  },
  hi: {
    bookVisit: "Site visit book karein",
    browseAll: "Sabhi projects dekhein",
    canBookVisit: "Ab aap is flat ke liye site visit book kar sakte hain.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor} par ek available flat chunein.`,
    chooseFloor: (wing) => `${wing} mein ek floor chunein.`,
    chooseProject: (count) => `Explore karne ke liye ek project chunein. ${count} live project${count === 1 ? " available hai" : "s available hain"}.`,
    chooseProjectInLocation: (count, location) => `${location} ke aas paas ye flats available hain. Explore karne ke liye ek project chunein. ${count} live project${count === 1 ? " available hai" : "s available hain"}.`,
    chooseWing: (project) => `${project} mein ek wing chunein.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing} mein abhi koi flat available nahi hai. Aap phir bhi site visit request kar sakte hain.`,
    noFlatsOnFloor: (floor) => `Floor ${floor} par abhi koi flat available nahi hai.`,
    noProjects: "Abhi koi live project available nahi hai.",
    noProjectsInLocation: (location) => `${location} ke aas paas abhi koi live project available nahi hai.`,
    noWings: (project) => `${project} mein abhi koi wing available nahi hai.`,
    priceNotListed: "Price listed nahi hai",
    saleableArea: "Saleable area",
    stepFailed: "Yeh step load nahi ho paaya. Kripya dobara try karein."
  },
  "hi-deva": {
    bookVisit: "साइट विज़िट बुक करें",
    browseAll: "सभी प्रोजेक्ट देखें",
    canBookVisit: "अब आप इस फ्लैट के लिए साइट विज़िट बुक कर सकते हैं।",
    carpetArea: "कारपेट एरिया",
    chooseFlat: (floor) => `फ्लोर ${floor} पर एक उपलब्ध फ्लैट चुनें।`,
    chooseFloor: (wing) => `${wing} में एक फ्लोर चुनें।`,
    chooseProject: (count) => `देखने के लिए एक प्रोजेक्ट चुनें। ${count} लाइव प्रोजेक्ट उपलब्ध हैं।`,
    chooseProjectInLocation: (count, location) => `${location} के आसपास उपलब्ध फ्लैट यहाँ हैं। देखने के लिए एक प्रोजेक्ट चुनें। ${count} लाइव प्रोजेक्ट उपलब्ध हैं।`,
    chooseWing: (project) => `${project} में एक विंग चुनें।`,
    flat: (unit) => `फ्लैट ${unit}`,
    floor: (floor) => `फ्लोर ${floor}`,
    livePrice: "लाइव कीमत",
    noFlatsInWing: (wing) => `${wing} में अभी कोई फ्लैट उपलब्ध नहीं है। आप फिर भी साइट विज़िट का अनुरोध कर सकते हैं।`,
    noFlatsOnFloor: (floor) => `फ्लोर ${floor} पर अभी कोई फ्लैट उपलब्ध नहीं है।`,
    noProjects: "अभी कोई लाइव प्रोजेक्ट उपलब्ध नहीं है।",
    noProjectsInLocation: (location) => `${location} के आसपास अभी कोई लाइव प्रोजेक्ट उपलब्ध नहीं है।`,
    noWings: (project) => `${project} में अभी कोई विंग उपलब्ध नहीं है।`,
    priceNotListed: "कीमत उपलब्ध नहीं है",
    saleableArea: "सेलेबल एरिया",
    stepFailed: "यह जानकारी लोड नहीं हो पाई। कृपया फिर से कोशिश करें।"
  },
  te: {
    bookVisit: "Site visit book cheyandi",
    browseAll: "Anni projects chudandi",
    canBookVisit: "Ippudu ee flat kosam site visit book cheyochu.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor} lo oka available flat select cheyandi.`,
    chooseFloor: (wing) => `${wing} lo oka floor select cheyandi.`,
    chooseProject: (count) => `Explore cheyadaniki oka project select cheyandi. ${count} live projects available unnayi.`,
    chooseProjectInLocation: (count, location) => `${location} chuttu prakkala available unna flats ivi. Explore cheyadaniki oka project select cheyandi. ${count} live projects available unnayi.`,
    chooseWing: (project) => `${project} lo oka wing select cheyandi.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing} lo ippudu flats available levu. Meeru site visit request cheyochu.`,
    noFlatsOnFloor: (floor) => `Floor ${floor} lo ippudu flats available levu.`,
    noProjects: "Ippudu live projects emi available levu.",
    noProjectsInLocation: (location) => `${location} chuttu prakkala ippudu live projects emi available levu.`,
    noWings: (project) => `${project} lo ippudu wings available levu.`,
    priceNotListed: "Price list cheyaledu",
    saleableArea: "Saleable area",
    stepFailed: "Ee step load avvaledu. Malli try cheyandi."
  },
  "te-telu": {
    bookVisit: "సైట్ విజిట్ బుక్ చేయండి",
    browseAll: "అన్ని ప్రాజెక్ట్‌లు చూడండి",
    canBookVisit: "ఇప్పుడు ఈ ఫ్లాట్ కోసం సైట్ విజిట్ బుక్ చేయవచ్చు.",
    carpetArea: "కార్పెట్ ఏరియా",
    chooseFlat: (floor) => `ఫ్లోర్ ${floor} లో అందుబాటులో ఉన్న ఒక ఫ్లాట్ ఎంచుకోండి.`,
    chooseFloor: (wing) => `${wing} లో ఒక ఫ్లోర్ ఎంచుకోండి.`,
    chooseProject: (count) => `చూడటానికి ఒక ప్రాజెక్ట్ ఎంచుకోండి. ${count} లైవ్ ప్రాజెక్ట్‌లు అందుబాటులో ఉన్నాయి.`,
    chooseProjectInLocation: (count, location) => `${location} చుట్టుపక్కల అందుబాటులో ఉన్న ఫ్లాట్‌లు ఇవి. చూడటానికి ఒక ప్రాజెక్ట్ ఎంచుకోండి. ${count} లైవ్ ప్రాజెక్ట్‌లు అందుబాటులో ఉన్నాయి.`,
    chooseWing: (project) => `${project} లో ఒక వింగ్ ఎంచుకోండి.`,
    flat: (unit) => `ఫ్లాట్ ${unit}`,
    floor: (floor) => `ఫ్లోర్ ${floor}`,
    livePrice: "లైవ్ ధర",
    noFlatsInWing: (wing) => `${wing} లో ప్రస్తుతం ఫ్లాట్‌లు అందుబాటులో లేవు. మీరు సైట్ విజిట్ అభ్యర్థించవచ్చు.`,
    noFlatsOnFloor: (floor) => `ఫ్లోర్ ${floor} లో ప్రస్తుతం ఫ్లాట్‌లు అందుబాటులో లేవు.`,
    noProjects: "ప్రస్తుతం లైవ్ ప్రాజెక్ట్‌లు అందుబాటులో లేవు.",
    noProjectsInLocation: (location) => `${location} చుట్టుపక్కల ప్రస్తుతం లైవ్ ప్రాజెక్ట్‌లు అందుబాటులో లేవు.`,
    noWings: (project) => `${project} లో ప్రస్తుతం వింగ్‌లు అందుబాటులో లేవు.`,
    priceNotListed: "ధర అందుబాటులో లేదు",
    saleableArea: "సేలబుల్ ఏరియా",
    stepFailed: "ఈ సమాచారం లోడ్ కాలేదు. దయచేసి మళ్లీ ప్రయత్నించండి."
  },
  ta: {
    bookVisit: "Site visit book pannunga",
    browseAll: "Ella projects-um paarunga",
    canBookVisit: "Indha flat-ku ippo site visit book pannalaam.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor}-la oru available flat select pannunga.`,
    chooseFloor: (wing) => `${wing}-la oru floor select pannunga.`,
    chooseProject: (count) => `Paarkka oru project select pannunga. ${count} live projects irukku.`,
    chooseProjectInLocation: (count, location) => `${location} pakkathula irukkura flats idho. Paarkka oru project select pannunga. ${count} live projects irukku.`,
    chooseWing: (project) => `${project}-la oru wing select pannunga.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing}-la ippo flats available illa. Neenga site visit request pannalaam.`,
    noFlatsOnFloor: (floor) => `Floor ${floor}-la ippo flats available illa.`,
    noProjects: "Ippo live projects edhuvum available illa.",
    noProjectsInLocation: (location) => `${location} pakkathula ippo live projects edhuvum illa.`,
    noWings: (project) => `${project}-la ippo wings available illa.`,
    priceNotListed: "Price list pannala",
    saleableArea: "Saleable area",
    stepFailed: "Indha step load aagala. Thirumba try pannunga."
  },
  kn: {
    bookVisit: "Site visit book maadi",
    browseAll: "Ella projects nodi",
    canBookVisit: "Ee flat-ge eega site visit book maadabahudu.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor} alli ondu available flat aayke maadi.`,
    chooseFloor: (wing) => `${wing} alli ondu floor aayke maadi.`,
    chooseProject: (count) => `Nodalu ondu project aayke maadi. ${count} live projects ive.`,
    chooseProjectInLocation: (count, location) => `${location} hattira iruva flats illive. Nodalu ondu project aayke maadi. ${count} live projects ive.`,
    chooseWing: (project) => `${project} alli ondu wing aayke maadi.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing} alli eega flats available illa. Neevu site visit request maadabahudu.`,
    noFlatsOnFloor: (floor) => `Floor ${floor} alli eega flats available illa.`,
    noProjects: "Eega yaava live projects available illa.",
    noProjectsInLocation: (location) => `${location} hattira eega yaava live projects illa.`,
    noWings: (project) => `${project} alli eega wings available illa.`,
    priceNotListed: "Price list maadilla",
    saleableArea: "Saleable area",
    stepFailed: "Ee step load aagalilla. Matte try maadi."
  },
  ml: {
    bookVisit: "Site visit book cheyyuka",
    browseAll: "Ella projects-um kaanuka",
    canBookVisit: "Ee flat-inu ippol site visit book cheyyaam.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor}-il oru available flat thiranjedukkuka.`,
    chooseFloor: (wing) => `${wing}-il oru floor thiranjedukkuka.`,
    chooseProject: (count) => `Kaanaan oru project thiranjedukkuka. ${count} live projects undu.`,
    chooseProjectInLocation: (count, location) => `${location}-inu aduthulla flats ivayaanu. Kaanaan oru project thiranjedukkuka. ${count} live projects undu.`,
    chooseWing: (project) => `${project}-il oru wing thiranjedukkuka.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing}-il ippol flats available illa. Ningalkku site visit request cheyyaam.`,
    noFlatsOnFloor: (floor) => `Floor ${floor}-il ippol flats available illa.`,
    noProjects: "Ippol live projects onnum available illa.",
    noProjectsInLocation: (location) => `${location}-inu aduthu ippol live projects onnum illa.`,
    noWings: (project) => `${project}-il ippol wings available illa.`,
    priceNotListed: "Price list cheythittilla",
    saleableArea: "Saleable area",
    stepFailed: "Ee step load aayilla. Veendum try cheyyuka."
  },
  mr: {
    bookVisit: "Site visit book kara",
    browseAll: "Sagle projects paha",
    canBookVisit: "Ya flat sathi aata site visit book karu shakta.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor} var ek available flat nivda.`,
    chooseFloor: (wing) => `${wing} madhye ek floor nivda.`,
    chooseProject: (count) => `Baghnyasathi ek project nivda. ${count} live projects uplabdh aahet.`,
    chooseProjectInLocation: (count, location) => `${location} javal uplabdh flats he aahet. Baghnyasathi ek project nivda. ${count} live projects uplabdh aahet.`,
    chooseWing: (project) => `${project} madhye ek wing nivda.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing} madhye sadhya flats uplabdh nahit. Tumhi site visit request karu shakta.`,
    noFlatsOnFloor: (floor) => `Floor ${floor} var sadhya flats uplabdh nahit.`,
    noProjects: "Sadhya konatehi live projects uplabdh nahit.",
    noProjectsInLocation: (location) => `${location} javal sadhya konatehi live projects nahit.`,
    noWings: (project) => `${project} madhye sadhya wings uplabdh nahit.`,
    priceNotListed: "Price list kelela nahi",
    saleableArea: "Saleable area",
    stepFailed: "Hi step load jhali nahi. Punha prayatna kara."
  },
  bn: {
    bookVisit: "Site visit book korun",
    browseAll: "Sob projects dekhun",
    canBookVisit: "Ei flat-er jonno ekhon site visit book korte paren.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor}-e ekta available flat bachhai korun.`,
    chooseFloor: (wing) => `${wing}-e ekta floor bachhai korun.`,
    chooseProject: (count) => `Dekhar jonno ekta project bachhai korun. ${count}-ti live project ache.`,
    chooseProjectInLocation: (count, location) => `${location}-er kachhe available flat gulo ei. Dekhar jonno ekta project bachhai korun. ${count}-ti live project ache.`,
    chooseWing: (project) => `${project}-e ekta wing bachhai korun.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing}-e ekhon kono flat available nei. Apni site visit request korte paren.`,
    noFlatsOnFloor: (floor) => `Floor ${floor}-e ekhon kono flat available nei.`,
    noProjects: "Ekhon kono live project available nei.",
    noProjectsInLocation: (location) => `${location}-er kachhe ekhon kono live project nei.`,
    noWings: (project) => `${project}-e ekhon kono wing available nei.`,
    priceNotListed: "Price list kora nei",
    saleableArea: "Saleable area",
    stepFailed: "Ei step load hoyni. Abar try korun."
  },
  gu: {
    bookVisit: "Site visit book karo",
    browseAll: "Badha projects juo",
    canBookVisit: "Aa flat mate have site visit book kari shako cho.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor} par ek available flat pasand karo.`,
    chooseFloor: (wing) => `${wing} ma ek floor pasand karo.`,
    chooseProject: (count) => `Jova mate ek project pasand karo. ${count} live projects uplabdh che.`,
    chooseProjectInLocation: (count, location) => `${location} ni aaspaas uplabdh flats aa rahya. Jova mate ek project pasand karo. ${count} live projects uplabdh che.`,
    chooseWing: (project) => `${project} ma ek wing pasand karo.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing} ma hal koi flat uplabdh nathi. Tame site visit request kari shako cho.`,
    noFlatsOnFloor: (floor) => `Floor ${floor} par hal koi flat uplabdh nathi.`,
    noProjects: "Hal koi live project uplabdh nathi.",
    noProjectsInLocation: (location) => `${location} ni aaspaas hal koi live project nathi.`,
    noWings: (project) => `${project} ma hal koi wing uplabdh nathi.`,
    priceNotListed: "Price list nathi",
    saleableArea: "Saleable area",
    stepFailed: "Aa step load na thayu. Fari try karo."
  },
  pa: {
    bookVisit: "Site visit book karo",
    browseAll: "Saare projects vekho",
    canBookVisit: "Is flat layi hun site visit book kar sakde ho.",
    carpetArea: "Carpet area",
    chooseFlat: (floor) => `Floor ${floor} te ik available flat chuno.`,
    chooseFloor: (wing) => `${wing} vich ik floor chuno.`,
    chooseProject: (count) => `Vekhan layi ik project chuno. ${count} live projects available ne.`,
    chooseProjectInLocation: (count, location) => `${location} de aas paas available flats eh ne. Vekhan layi ik project chuno. ${count} live projects available ne.`,
    chooseWing: (project) => `${project} vich ik wing chuno.`,
    flat: (unit) => `Flat ${unit}`,
    floor: (floor) => `Floor ${floor}`,
    livePrice: "Live price",
    noFlatsInWing: (wing) => `${wing} vich hun koi flat available nahi. Tusi site visit request kar sakde ho.`,
    noFlatsOnFloor: (floor) => `Floor ${floor} te hun koi flat available nahi.`,
    noProjects: "Hun koi live project available nahi.",
    noProjectsInLocation: (location) => `${location} de aas paas hun koi live project nahi.`,
    noWings: (project) => `${project} vich hun koi wing available nahi.`,
    priceNotListed: "Price list nahi kita",
    saleableArea: "Saleable area",
    stepFailed: "Eh step load nahi hoya. Dubara try karo."
  }
};
