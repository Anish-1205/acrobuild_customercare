export type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal?: boolean }> }) => void) | null;
  start: () => void;
  stop: () => void;
};

export type SpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

export const VOICE_LANGUAGES = {
  "as-IN": "Assamese", "bn-IN": "Bengali", "brx-IN": "Bodo", "doi-IN": "Dogri",
  "en-IN": "English (India)", "gu-IN": "Gujarati", "hi-IN": "Hindi", "kn-IN": "Kannada",
  "kok-IN": "Konkani", "mai-IN": "Maithili", "ml-IN": "Malayalam", "mni-IN": "Manipuri",
  "mr-IN": "Marathi", "ne-NP": "Nepali", "or-IN": "Odia", "pa-IN": "Punjabi",
  "sa-IN": "Sanskrit", "sat-IN": "Santali", "sd-IN": "Sindhi", "ta-IN": "Tamil",
  "te-IN": "Telugu", "ur-IN": "Urdu"
} as const;

export type VoiceLanguageCode = keyof typeof VOICE_LANGUAGES;

export function resolveVoiceLanguage(issue: string, selectedLanguage: VoiceLanguageCode): VoiceLanguageCode {
  if (selectedLanguage !== "en-IN") {
    return selectedLanguage;
  }

  const normalizedIssue = issue.toLowerCase().replace(/[^a-z\s]/g, " ");
  const romanizedTeluguTerms = [
    "chestunnav", "chestunav", "enti", "emiti", "ela", "unnava", "unnaru",
    "naku", "naaku", "kavali", "kaavali", "cheppu", "cheppandi", "avunu",
    "ledu", "enduku", "eppudu", "ekkada", "bagunnara", "namaskaram"
  ];

  if (romanizedTeluguTerms.some((term) => normalizedIssue.split(/\s+/).includes(term))) {
    return "te-IN";
  }

  if (/[\u0C00-\u0C7F]/.test(issue)) {
    return "te-IN";
  }

  return selectedLanguage;
}

export function detectSpeechLanguage(text: string, selectedLanguage: VoiceLanguageCode): VoiceLanguageCode {
  if (selectedLanguage !== "en-IN") {
    return selectedLanguage;
  }

  const scriptLanguages: Array<[RegExp, VoiceLanguageCode]> = [
    [/[\u0980-\u09FF]/, "bn-IN"],
    [/[\u0900-\u097F]/, "hi-IN"],
    [/[\u0A00-\u0A7F]/, "pa-IN"],
    [/[\u0A80-\u0AFF]/, "gu-IN"],
    [/[\u0B00-\u0B7F]/, "or-IN"],
    [/[\u0B80-\u0BFF]/, "ta-IN"],
    [/[\u0C00-\u0C7F]/, "te-IN"],
    [/[\u0C80-\u0CFF]/, "kn-IN"],
    [/[\u0D00-\u0D7F]/, "ml-IN"],
    [/[\u0600-\u06FF]/, "ur-IN"],
  ];
  return scriptLanguages.find(([pattern]) => pattern.test(text))?.[1] ?? selectedLanguage;
}
export function buildVoiceAssistIssue(issue: string, languageCode: VoiceLanguageCode) {
  const languageName = VOICE_LANGUAGES[languageCode];
  return languageCode === "te-IN"
    ? `${issue}\n\nVoice language: Telugu. Reply in natural conversational Telugu-English (Tenglish): use Telugu sentence structure with familiar English words like update, payment, ticket, email, project, status, photos, and support. Keep Telugu in Telugu script, English terms in English. Sound like a helpful Hyderabad support agent, not formal or literary. Use 2-4 short sentences. Never say Good day, relevant information, most certainly, or further assistance.`
    : `${issue}\n\nVoice language: ${languageName}. Reply naturally in the customer's language, keeping common product and support terms in English.`;
}
