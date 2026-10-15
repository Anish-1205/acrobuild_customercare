import { expect, test } from "@playwright/test";

test("customer chat shows discovery questions, grounded qualifiers, and wildcard buttons", async ({ page }) => {
  const answers = [
    {
      answer: [
        "We have two projects listing 3BHK homes in Pune and Thane.",
        "These are catalogue listings; I haven't checked current unit availability yet.",
        'Which location would you like to explore? You can also say "any area".',
        "- Pune",
        "- Thane"
      ].join("\n"),
      quick_replies: [
        { label: "Pune", value: "Pune" },
        { label: "Thane", value: "Thane" },
        { label: "Any area", value: "Any area" }
      ]
    },
    {
      answer: [
        "We have two projects listed with 3BHK configurations.",
        "These are catalogue listings; I haven't checked current unit availability yet.",
        "Do you have a budget limit, or should I include all prices?",
        "Feel free to type your budget in the chat (for example, INR 1.5 crore)."
      ].join("\n"),
      quick_replies: [{ label: "Any budget", value: "any budget" }]
    },
    {
      answer: [
        "We've got two matching projects.",
        "3BHK projects (estimated base amount):",
        "- Acro Iris: estimated base amount from INR 1.20 crore",
        "- Acro Tulip: estimated base amount from INR 1.40 crore",
        "Estimated base amount excludes taxes, registration, floor rise and parking.",
        "Select a project and I'll check its current details and availability."
      ].join("\n"),
      quick_replies: [
        { label: "Acro Iris", value: "Acro Iris" },
        { label: "Acro Tulip", value: "Acro Tulip" }
      ]
    }
  ];
  const issues: string[] = [];
  let turn = 0;

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch" && request.resourceType() !== "xhr") {
      return route.continue();
    }
    const path = new URL(request.url()).pathname;
    if (path === "/api/support/assist/stream") {
      issues.push(JSON.parse(request.postData() ?? "{}").issue);
      const response = answers[turn++];
      return route.fulfill({
        body: JSON.stringify({ type: "done", response }) + "\n",
        contentType: "application/x-ndjson",
        status: 200
      });
    }
    if (path.includes("/conversations/") && path.endsWith("/history")) {
      return route.fulfill({ json: { exists: false, messages: [], quick_replies: [] } });
    }
    if (path.includes("/articles")) return route.fulfill({ json: { articles: [] } });
    return route.fulfill({ json: {} });
  });

  await page.goto("/home", { waitUntil: "domcontentloaded" });
  await page.getByRole("textbox", { name: "Message Acrobuild Assistant" }).fill("Show me 3 BHK");
  await page.getByRole("button", { name: "Send message" }).click();
  const chat = page.getByRole("dialog", { name: "Acrobuild Assistant" });
  await expect(chat.getByText("Which location would you like to explore?", { exact: false })).toBeVisible();
  await expect(chat.getByText("I haven't checked current unit availability yet.", { exact: false })).toBeVisible();
  await expect(chat.getByRole("button", { name: "Any area" })).toBeVisible();
  await chat.getByRole("button", { name: "Any area" }).click();

  await expect(chat.getByText("Do you have a budget limit, or should I include all prices?", { exact: false })).toBeVisible();
  await expect(chat.getByRole("button", { name: "Any budget" })).toBeVisible();
  await chat.getByRole("button", { name: "Any budget" }).click();

  await expect(chat.getByText("Acro Iris: estimated base amount from INR 1.20 crore", { exact: false })).toBeVisible();
  await expect(chat.getByText("Estimated base amount excludes taxes", { exact: false })).toBeVisible();
  expect(issues).toEqual(["Show me 3 BHK", "Any area", "any budget"]);
});
