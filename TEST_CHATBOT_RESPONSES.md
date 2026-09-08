# Quick Test Guide - Butler-Style Responses

## 🚀 Start the Chatbot

```bash
cd e:\customer-support-agent
uvicorn app:api --reload
```

The API will run on: `http://localhost:8000`

---

## 🧪 Test Cases

### Test 1️⃣: TELUGU - Site Visit Booking

**Query:**
```bash
curl -X POST "http://localhost:8000/create_ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "customer@example.com",
    "subject": "Site visit booking",
    "description": "Naino Ki site visit booking appointment Kabali Voice language: telugu."
  }'
```

**Expected Response:**
```
నమస్తే! Good day. I can help arrange a site visit. 
Might I kindly request that you share the project or 
property name, your preferred date and time, and the 
best phone number for confirmation. I remain at your 
service should you require further assistance.
```

✅ Should be:
- [x] Telugu greeting only (నమస్తే)
- [x] Rest in professional English
- [x] Easy to read
- [x] NOT full Telugu script

---

### Test 2️⃣: HINDI - Order Status

**Query:**
```bash
curl -X POST "http://localhost:8000/create_ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "customer@example.com",
    "subject": "मेरे ऑर्डर की स्थिति",
    "description": "मेरा ऑर्डर कहाँ है? Voice language: hindi."
  }'
```

**Expected Response:**
```
नमस्ते! Good day. Your order is most certainly being 
processed and will arrive soon. Might I suggest 
tracking your shipment through our website? 
I remain at your service.
```

✅ Should be:
- [x] Hindi greeting only (नमस्ते)
- [x] Rest in English
- [x] Professional tone
- [x] NOT full Hindi script

---

### Test 3️⃣: TAMIL - Account Query

**Query:**
```bash
curl -X POST "http://localhost:8000/create_ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "customer@example.com",
    "subject": "என் கணக்கு",
    "description": "என் கணக்கு பற்றி சந்தேகம் உள்ளது Voice language: tamil."
  }'
```

**Expected Response:**
```
வணக்கம்! Good day. I would be delighted to assist 
with your account inquiry. Might I kindly request 
the specific details of your concern? 
I remain at your service.
```

✅ Should be:
- [x] Tamil greeting only (வணக்கம்)
- [x] Rest in English
- [x] Clear and readable
- [x] NOT full Tamil script

---

### Test 4️⃣: ENGLISH - Standard Query

**Query:**
```bash
curl -X POST "http://localhost:8000/create_ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "customer@example.com",
    "subject": "Order Status",
    "description": "Where is my order? I ordered it 2 days ago."
  }'
```

**Expected Response:**
```
Good day. Your order is most certainly being processed 
and will arrive soon. Might I suggest tracking your 
shipment through our website for the latest updates? 
I remain at your service should you require further assistance.
```

✅ Should be:
- [x] NO greeting (already English)
- [x] Professional English throughout
- [x] Butler-style politeness
- [x] Easy to read

---

### Test 5️⃣: KANNADA - Billing Question

**Query:**
```bash
curl -X POST "http://localhost:8000/create_ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "customer@example.com",
    "subject": "ಬಿಲ್ಲಿಂಗ್",
    "description": "ನನ್ನ ಬಿಲ್ ಮುಂದಿನ ತಿಂಗಳುದ್ದಕ್ಕೆ ತಿತ್ತಿರಲಿ Voice language: kannada."
  }'
```

**Expected Response:**
```
ನಮಸ್ಕಾರ! Good day. I understand your billing concern. 
Our accounting team will review your account and 
respond within 24 hours. I remain at your service.
```

✅ Should be:
- [x] Kannada greeting only (ನಮಸ್ಕಾರ)
- [x] Rest in English
- [x] Professional and clear
- [x] NOT full Kannada script

---

## ❌ What Should NOT Happen

**WRONG - Full Script (OLD BROKEN)**:
```
❌ నాకు ఒక సైట్ విజిట్ చేయించగలను ఒపరేషన్‌లకు...
   తీర్పులంగా, నీ సైట్ విజిట్ అప్‌లూకెషన్‌ మీ నుచెహనం చేస్సు.
   (FULL TELUGU - HARD TO READ)
```

**WRONG - Mixed Scripts**:
```
❌ नमस्ते! मेरा आर्डर तैयार है। 
   Your order is ready. 
   आपकी पुष्टि ईमेल की जांच करें।
   (MIXED HINDI-ENGLISH - CONFUSING)
```

**CORRECT - Butler English**:
```
✅ नमस्ते! Good day. Your order is most certainly 
   prepared. Might I suggest reviewing your 
   confirmation email? I remain at your service.
   (GREETING + PROFESSIONAL ENGLISH)
```

---

## 🧑‍💻 Manual Testing Without curl

### Using Python:
```python
import requests

response = requests.post(
    "http://localhost:8000/create_ticket",
    json={
        "email": "test@example.com",
        "subject": "Order Status",
        "description": "Where is my order? Voice language: telugu."
    }
)

print(response.json())
```

### Expected JSON Response:
```json
{
  "ticket_id": "TKT-12345",
  "status": "created",
  "message": "నమస్తే! Good day. Your order is most certainly...",
  "language": "telugu",
  "priority": "medium",
  "agent": "Tom"
}
```

---

## ✅ Verification Checklist

For each test, verify:

- [ ] Greeting in correct language (only)
- [ ] Main response in professional English
- [ ] Response is readable and clear
- [ ] No full script translations
- [ ] Butler-style tone present
- [ ] Ends with "I remain at your service"
- [ ] No technical jargon or system info
- [ ] Response is concise and helpful

---

## 📊 Response Quality Metrics

### Good Response ✅
- Greeting: 1 word in target language
- English percentage: 95%+
- Readability: High (no script confusion)
- Professional: Yes
- Helpful: Yes
- Accurate: Yes

### Bad Response ❌
- Greeting: Multiple words or mixed
- English percentage: <80%
- Readability: Low (confusing scripts)
- Professional: No
- Helpful: Unclear
- Accurate: No

---

## 🐛 Troubleshooting

### Issue: Still showing FULL TELUGU SCRIPT
**Solution**: 
1. Restart the application
2. Verify `ai_agent_service.py` has butler functions
3. Check that `localize_ai_answer()` is being called

### Issue: Greeting not appearing
**Solution**:
1. Verify language is detected: `Voice language: telugu.`
2. Check `extract_voice_response_language()` works
3. Ensure issue text contains language marker

### Issue: Butler politeness not applied
**Solution**:
1. Verify `add_butler_politeness()` is in code
2. Check `create_butler_english_response()` is called
3. Inspect response structure

---

## 📞 Expected Response Flow

```
User Query (any language)
    ↓
System detects language
    ↓
LLM generates response (with butler system prompt)
    ↓
Extract language preference
    ↓
Get language greeting
    ↓
Apply butler politeness
    ↓
Combine: greeting + "Good day" + response + closing
    ↓
Return to user
```

---

## 🎯 Success Criteria

Your fix is working when:

1. ✅ Telugu/Hindi/Tamil responses are in **English**
2. ✅ Only **one word greeting** in target language
3. ✅ Response is **readable and professional**
4. ✅ **NO full script** anywhere in response
5. ✅ **Butler-like tone** throughout
6. ✅ **Easy to understand** for all users

---

**Status**: Ready for testing! 🚀
