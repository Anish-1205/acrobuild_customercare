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
