import { describe, expect, it } from "vitest";
import { FLOW_TEXT, chatLanguageFromReply, detectChatLanguage, extractLocationHint, isProjectBrowseRequest } from "./chatLanguage";

describe("detectChatLanguage", () => {
  it.each([
    ["aapke paas konse projects available hai ?", "hi"],
    ["telugu lo discuss chedham", "te"],
    ["प्रोजेक्ट दिखाइए", "hi-deva"],
    ["ప్రాజెక్ట్‌లు చూపించండి", "te-telu"],
    ["which projects are available?", "en"],
    ["nee peru enti ?", "te"],
    ["nee yenna pandre", "ta"],
    ["neevu hegiddira", "kn"],
    ["ningalude peru enthanu", "ml"],
    ["marathi madhe bol", "mr"],
    ["tumi kemon acho", "bn"],
    ["tame kem cho", "gu"],
    ["tusi kiddan ho", "pa"],
    ["english lo cheppu", "en"],
    ["உங்கள் பெயர் என்ன", "ta"]
  ] as const)("detects %s", (text, expected) => {
    expect(detectChatLanguage(text, "en-IN", "en")).toBe(expected);
  });

  it("keeps the previous language for bare selections", () => {
    expect(detectChatLanguage("Vishwajeet Prime", "en-IN", "hi")).toBe("hi");
    expect(detectChatLanguage("3", "en-IN", "te")).toBe("te");
  });

  it("uses the selected voice language", () => {
    expect(detectChatLanguage("hello", "ta-IN", "en")).toBe("ta");
  });

  it("distinguishes native-script Marathi from Hindi (shared Devanagari script)", () => {
    expect(detectChatLanguage("ठाण्यात तुमच्या कोणत्या मालमत्ता आहेत?", "en-IN", "en")).toBe("mr");
    expect(detectChatLanguage("मुझे 2 BHK फ्लैट चाहिए", "en-IN", "en")).toBe("hi-deva");
  });
});

describe("chatLanguageFromReply", () => {
  it.each([
    ["Telugu", "latin", "te"],
    ["Telugu", "native", "te-telu"],
    ["Hindi", "native", "hi-deva"],
    ["Marathi", "latin", "mr"],
    ["English", "latin", "en"]
  ] as const)("maps %s/%s", (language, script, expected) => {
    expect(chatLanguageFromReply(language, script, "en")).toBe(expected);
  });

  it("keeps the previous language for languages without flow text", () => {
    expect(chatLanguageFromReply("Odia", "latin", "hi")).toBe("hi");
    expect(chatLanguageFromReply(undefined, undefined, "te")).toBe("te");
  });
});

describe("isProjectBrowseRequest", () => {
  it.each([
    "aapke paas konse projects available hai ?",
    "kaunse projects hai aapke paas",
    "aapke paas kya flats available hai ?",
    "which projects are available?",
    "projects",
    "ఏ ప్రాజెక్ట్‌లు ఉన్నాయి",
    "कौन से प्रोजेक्ट उपलब्ध हैं",
    "what flats do you have in mumbai",
    "which projects are available in pune?",
    "flats available in vishwajeet heights"
  ])("opens the menu for %s", (text) => {
    expect(isProjectBrowseRequest(text)).toBe(true);
  });

  it.each([
    "2bhk flats available",
    "what is the price of flats",
    "telugu lo discuss chedham",
    "what is the capital of australia?",
    "what is the location of vishwajeet prime"
  ])("does not open the menu for %s", (text) => {
    expect(isProjectBrowseRequest(text)).toBe(false);
  });

  it("does not open the menu when a known project is named", () => {
    expect(isProjectBrowseRequest("Vishwajeet Prime flats available", ["Vishwajeet Prime"])).toBe(false);
    expect(isProjectBrowseRequest("flats available in vishwajeet heights", ["Vishwajeet Heights"])).toBe(false);
  });
});

describe("extractLocationHint", () => {
  it.each([
    ["what flats do you have in mumbai", "Mumbai"],
    ["which projects are available in pune?", "Pune"],
    ["flats near thane", "Thane"],
    ["projects available at andheri east", "Andheri East"],
    ["thane lo flats chupinchu", "Thane"],
    ["pune mein projects dikhao", "Pune"],
    ["kalyan madhe flats dakhva", "Kalyan"],
    ["chennai la flats irukka", "Chennai"],
    ["ambernath vich projects dasso", "Ambernath"]
  ])("extracts %s -> %s", (text, expected) => {
    expect(extractLocationHint(text)).toBe(expected);
  });

  it.each([
    "which projects are available?",
    "2bhk flats available",
    "projects",
    "show me flats",
    "telugu lo projects chupinchu",
    "flats lo emi unnayi"
  ])("returns null for %s", (text) => {
    expect(extractLocationHint(text)).toBeNull();
  });
});

it("has every flow string for every language", () => {
  const englishKeys = Object.keys(FLOW_TEXT.en).sort();
  for (const text of Object.values(FLOW_TEXT)) {
    expect(Object.keys(text).sort()).toEqual(englishKeys);
  }
});
