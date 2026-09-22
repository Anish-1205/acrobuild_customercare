"""Generate 300 reproducible freechat evaluation cases (no model calls)."""
import csv
import json
import re
from pathlib import Path


# Five parallel general-chat questions, then five deliberately underspecified ones.
# Native script and Latin transliteration are authored separately.
LANGUAGES = {
    "English": (
        "What is your name?|Why is the sky blue?|How much is 12 plus 7?|Can you tell a short story about a cat?|Can you explain photosynthesis simply?",
        "What is your name?|Why is the sky blue?|How much is 12 plus 7?|Can you tell a short story about a cat?|Can you explain photosynthesis simply?",
        "Can you explain that?|Which one is better?|Can you translate it?|What does bat mean?|Can you make it shorter?",
    ),
    "Hindi": (
        "आपका नाम क्या है?|आसमान नीला क्यों है?|12 और 7 का जोड़ कितना है?|क्या आप बिल्ली की छोटी कहानी सुना सकते हैं?|क्या आप प्रकाश संश्लेषण सरल भाषा में समझा सकते हैं?",
        "aapka naam kya hai?|aasman neela kyon hai?|12 aur 7 ka jod kitna hai?|kya aap billi ki chhoti kahani suna sakte hain?|kya aap prakash sanshleshan aasan bhasha mein samjha sakte hain?",
        "kya aap woh samjha sakte hain?|kaunsa behtar hai?|kya aap iska anuvad kar sakte hain?|bat ka matlab kya hai?|kya aap ise chhota kar sakte hain?",
    ),
    "Telugu": (
        "మీ పేరు ఏమిటి?|ఆకాశం నీలంగా ఎందుకు ఉంటుంది?|12 కి 7 కలిపితే ఎంత?|పిల్లి గురించి చిన్న కథ చెప్పగలరా?|కిరణజన్య సంయోగక్రియను సులభంగా వివరించగలరా?",
        "mee peru emiti?|aakasam neelanga enduku untundi?|12 ki 7 kalipithe entha?|pilli gurinchi chinna katha cheppagalara?|kirana janya samyoga kriyanu sulabhanga vivarinchagalara?",
        "adi vivarinchagalara?|edi manchidi?|danni anuvadinchagalara?|bat ante emiti?|danni chinnaga cheppagalara?",
    ),
    "Tamil": (
        "உங்கள் பெயர் என்ன?|வானம் ஏன் நீலமாக இருக்கிறது?|12 உடன் 7 சேர்த்தால் எவ்வளவு?|பூனை பற்றிய சிறிய கதை சொல்ல முடியுமா?|ஒளிச்சேர்க்கையை எளிமையாக விளக்க முடியுமா?",
        "ungal peyar enna?|vaanam yen neelamaaga irukkirathu?|12 udan 7 serthaal evvalavu?|poonai patriya siriya kathai solla mudiyuma?|olichcherkkaiyai elimaiyaaga vilakka mudiyuma?",
        "athai vilakka mudiyuma?|ethu sirandhathu?|athai mozhipeyarkka mudiyuma?|bat endraal enna?|athai surukkamaaga solla mudiyuma?",
    ),
    "Marathi": (
        "तुमचे नाव काय आहे?|आकाश निळे का असते?|12 आणि 7 यांची बेरीज किती?|मांजरीची छोटी गोष्ट सांगाल का?|प्रकाशसंश्लेषण सोप्या भाषेत समजावून सांगाल का?",
        "tumche naav kay aahe?|aakash nile ka aste?|12 aani 7 yanchi berij kiti?|manjarichi chhoti goshta sangal ka?|prakash sanshleshan sopya bhashet samjavun sangal ka?",
        "te samjavun sangal ka?|konte changle aahe?|tyache bhashantar karal ka?|bat cha arth kay aahe?|te thodkyat sangal ka?",
    ),
    "Bengali": (
        "আপনার নাম কী?|আকাশ নীল কেন?|12 আর 7 যোগ করলে কত হয়?|বিড়াল নিয়ে ছোট গল্প বলতে পারেন?|সালোকসংশ্লেষ সহজভাবে বোঝাতে পারেন?",
        "apnar naam ki?|akash nil keno?|12 ar 7 jog korle koto hoy?|biral niye chhoto golpo bolte paren?|salok songshlesh sohoj bhabe bojhate paren?",
        "ota bojhate paren?|konta bhalo?|otar onubad korte paren?|bat mane ki?|ota chhoto kore bolte paren?",
    ),
    "Gujarati": (
        "તમારું નામ શું છે?|આકાશ વાદળી કેમ છે?|12 અને 7 નો સરવાળો કેટલો થાય?|બિલાડી વિશે નાની વાર્તા કહેશો?|પ્રકાશસંશ્લેષણ સરળ રીતે સમજાવશો?",
        "tamaru naam shu chhe?|aakash vadali kem chhe?|12 ane 7 no sarvalo ketlo thay?|biladi vishe nani varta kahesho?|prakash sanshleshan saral rite samjavsho?",
        "te samjavsho?|kayu saru chhe?|teno anuvad karsho?|bat no arth shu chhe?|te tunkama kahesho?",
    ),
    "Kannada": (
        "ನಿಮ್ಮ ಹೆಸರೇನು?|ಆಕಾಶ ನೀಲಿಯಾಗಿ ಏಕೆ ಕಾಣುತ್ತದೆ?|12 ಮತ್ತು 7 ಕೂಡಿಸಿದರೆ ಎಷ್ಟು?|ಬೆಕ್ಕಿನ ಬಗ್ಗೆ ಚಿಕ್ಕ ಕಥೆ ಹೇಳುವಿರಾ?|ದ್ಯುತಿಸಂಶ್ಲೇಷಣೆಯನ್ನು ಸರಳವಾಗಿ ವಿವರಿಸುವಿರಾ?",
        "nimma hesarenu?|aakasha neeliyagi eke kaanuttade?|12 mattu 7 kudisidare eshtu?|bekkina bagge chikka kathe helu vira?|dyuti samshleshaneyannu saralavagi vivarisu vira?",
        "adannu vivarisu vira?|yaavudu uttama?|adannu anuvadisu vira?|bat andare enu?|adannu chikkadagi helu vira?",
    ),
    "Malayalam": (
        "നിങ്ങളുടെ പേരെന്താണ്?|ആകാശം നീലയായിരിക്കുന്നത് എന്തുകൊണ്ട്?|12 ഉം 7 ഉം കൂട്ടിയാൽ എത്ര?|പൂച്ചയെക്കുറിച്ച് ഒരു ചെറിയ കഥ പറയാമോ?|പ്രകാശസംശ്ലേഷണം ലളിതമായി വിശദീകരിക്കാമോ?",
        "ningalude perenthaanu?|aakasham neelayaayirikkunnathu enthukondu?|12 um 7 um koottiyaal ethra?|poochaye kurichu oru cheriya katha parayaamo?|prakasha samshleshanam lalithamaayi vishadeekarikkaamo?",
        "athu vishadeekarikkaamo?|ethaanu nallathu?|athu vivarthanam cheyyaamo?|bat ennaal enthaanu?|athu churukki parayaamo?",
    ),
    "Punjabi": (
        "ਤੁਹਾਡਾ ਨਾਮ ਕੀ ਹੈ?|ਅਸਮਾਨ ਨੀਲਾ ਕਿਉਂ ਹੈ?|12 ਅਤੇ 7 ਦਾ ਜੋੜ ਕਿੰਨਾ ਹੈ?|ਬਿੱਲੀ ਬਾਰੇ ਛੋਟੀ ਕਹਾਣੀ ਸੁਣਾ ਸਕਦੇ ਹੋ?|ਪ੍ਰਕਾਸ਼ ਸੰਸ਼ਲੇਸ਼ਣ ਸੌਖੇ ਤਰੀਕੇ ਨਾਲ ਸਮਝਾ ਸਕਦੇ ਹੋ?",
        "tuhada naam ki hai?|asmaan neela kyon hai?|12 ate 7 da jor kinna hai?|billi bare chhoti kahani suna sakde ho?|prakash sanshleshan saukhe tarike naal samjha sakde ho?",
        "oh samjha sakde ho?|kehda changa hai?|ohda anuvad kar sakde ho?|bat da matlab ki hai?|oh chhota kar sakde ho?",
    ),
}

ANSWERS = [
    "Identify as Acrobuild Support, an AI assistant; do not invent a human identity.",
    "Explain that air scatters blue sunlight more strongly than red sunlight.",
    "Answer 19; preserve both input numbers.",
    "Tell a short original story about a cat.",
    "Explain that plants use light, water and carbon dioxide to make food, releasing oxygen.",
]
CLARIFICATIONS = [
    "Ask what 'that' refers to; there is no prior topic.",
    "Ask which options the user wants compared and by what criterion.",
    "Ask for the text to translate and the target language.",
    "Ask whether 'bat' means the animal or sporting equipment; mentioning both senses is acceptable.",
    "Ask for the text to shorten; there is no previous answer to summarize.",
]


def add_typo(text, index):
    """One controlled Latin-word edit; never alter numbers or the ambiguous 'bat'."""
    words = list(re.finditer(r"[A-Za-z]{4,}", text))
    word = max(words, key=lambda match: len(match.group()))
    original = word.group()
    if index % 3 == 0:
        replacement = original[:2] + original[3:]
        edit = "single_character_deletion"
    elif index % 3 == 1:
        replacement = original[:2] + original[1] + original[2:]
        edit = "single_character_insertion"
    else:
        replacement = original[:1] + original[2] + original[1] + original[3:]
        edit = "adjacent_transposition"
        if replacement == original:
            replacement = original[:-1] + "x"
            edit = "single_character_substitution"
    return text[:word.start()] + replacement + text[word.end():], edit


def build_rows():
    rows = []
    for language, (native, romanized, ambiguous) in LANGUAGES.items():
        for index, (native_text, roman_text, ambiguous_text) in enumerate(
            zip(native.split("|"), romanized.split("|"), ambiguous.split("|"))
        ):
            typo, edit = add_typo(roman_text, index)
            ambiguous_typo, ambiguous_edit = add_typo(ambiguous_text, index)
            variants = [
                ("native_script" if language != "English" else "standard_english", native_text, native_text, "none", False, "native" if language != "English" else "latin"),
                ("romanized" if language != "English" else "casual_english", roman_text if language != "English" else roman_text.lower(), roman_text, "none", False, "latin"),
                ("mixed_language" if language != "English" else "explicit_language", f"{roman_text} Please reply in {language} using English letters.", roman_text, "none", False, "latin"),
                ("typo", typo, roman_text, edit, False, "latin"),
                ("ambiguous", ambiguous_text, ambiguous_text, "none", True, "latin"),
                ("ambiguous_typo", ambiguous_typo, ambiguous_text, ambiguous_edit, True, "latin"),
            ]
            for category, prompt, normalized, typo_type, is_ambiguous, script in variants:
                rows.append({
                    "test_id": f"FC{len(rows) + 1:03d}",
                    "scope": "freechat_only",
                    "language": language,
                    "category": category,
                    "user_input": prompt,
                    "normalized_input": normalized,
                    "conversation_messages": "[]",
                    "expected_intent": "general",
                    "expected_reply_language": language,
                    "expected_reply_script": script,
                    "expected_action": "clarify" if is_ambiguous else "answer",
                    "expected_behavior": CLARIFICATIONS[index] if is_ambiguous else ANSWERS[index],
                    "typo_type": typo_type,
                    "typo_tolerance": "medium",
                })
    assert len(rows) == 300
    assert len({row["user_input"] for row in rows}) == 300
    return rows


def main():
    target = Path(__file__).resolve().parents[1] / "data" / "evaluation"
    target.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with (target / "freechat_multilingual_300.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (target / "freechat_multilingual_300.json").write_text(
        json.dumps([{**row, "conversation_messages": []} for row in rows], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} cases to {target}")


if __name__ == "__main__":
    main()
