import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

type StaffRole = "admin" | "owner" | "agent";

const viewports = [
  { height: 900, name: "large desktop", width: 1440 },
  { height: 800, name: "laptop", width: 1280 },
  { height: 1024, name: "tablet", width: 768 },
  { height: 844, name: "mobile", width: 390 },
  { height: 720, name: "narrow mobile", width: 320 }
];

const publicRoutes = [
  "/home",
  "/home/about",
  "/home/categories/site-visit",
  "/home/categories/not-a-category",
  "/home/articles/1-site-visit-booking-checklist",
  "/home/articles/not-an-article",
  "/home/project-support",
  "/home/order-lookup",
  "/home/api-activity",
  "/home/data-api-logs",
  "/login"
];

const adminRoutes = [
  "/admin/inbox",
  "/admin/workspace?panel=ai-agent",
  "/admin/workspace?panel=articles",
  "/admin/workspace?panel=chat-widget",
  "/admin/workspace?panel=business-hours",
  "/admin/workspace?panel=macros",
  "/admin/workspace?panel=manage-tags",
  "/admin/workspace?panel=users",
  "/admin/workspace?panel=cs-api-settings",
  "/admin/workspace?panel=analytics",
  "/admin/workspace?panel=ticket-dashboard",
  "/admin/workspace?panel=api-activity",
  "/admin/workspace?panel=data-api-logs",
  "/admin/automation"
];

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    body: JSON.stringify(body),
    contentType: "application/json",
    status
  });
}

async function mockBrowserApis(page: Page, role: StaffRole | null = null) {
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (request.resourceType() !== "fetch" && request.resourceType() !== "xhr") {
      return route.continue();
    }

    if (path === "/auth/me") {
      return role
        ? json(route, {
            user: {
              email: `${role}@example.test`,
              id: 1,
              name: `${role[0].toUpperCase()}${role.slice(1)} User`,
              role,
              status: "Active",
              team: "Support"
            }
          })
        : json(route, { detail: "Not authenticated" }, 401);
    }

    if (path === "/auth/refresh") return json(route, { detail: "Not authenticated" }, 401);
    if (path.includes("/tickets")) return json(route, { limit: 500, offset: 0, tickets: [], total: 0 });
    if (path.includes("/knowledge-documents")) return json(route, { documents: [] });
    if (path.includes("/articles")) return json(route, { articles: [] });
    if (path.includes("/business-hours/profiles")) return json(route, { profiles: [] });
    if (path.includes("/automation/escalations")) return json(route, { tickets: [] });
    if (path.includes("/automation/capacity")) return json(route, { agents: [] });
    if (path.includes("/cs-api-settings")) {
      return json(route, { api_key_configured: false, base_url: "", company_id: "" });
    }
    if (path.includes("/macros")) return json(route, { macros: [] });
    if (path.includes("/tags")) return json(route, { tags: [] });
    if (path.includes("/users")) return json(route, { users: [] });
    if (path.includes("/conversations/")) return json(route, { conversation_id: "mock", messages: [] });
    return json(route, {});
  });
}

async function expectNoPageOverflow(page: Page, route: string, viewportName: string) {
  const overflow = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth
  }));
  expect.soft(
    overflow.scrollWidth,
    `${route} at ${viewportName} has horizontal page overflow`
  ).toBeLessThanOrEqual(overflow.clientWidth + 1);
}

async function expectNoSeriousAxeFindings(page: Page, route: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = results.violations.filter(({ impact }) => impact === "serious" || impact === "critical");
  expect.soft(
    serious.map(({ help, id, nodes }) => ({ help, id, targets: nodes.map((node) => node.target) })),
    `${route} has serious or critical axe findings`
  ).toEqual([]);
}

test("public and login routes fit the Phase 7 viewport matrix", async ({ page }) => {
  await mockBrowserApis(page);

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    for (const route of publicRoutes) {
      await page.goto(route);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator("h1")).toBeVisible();
      await expectNoPageOverflow(page, route, viewport.name);
    }
  }
});

test("public, chat, and login accessibility smoke", async ({ page }) => {
  await mockBrowserApis(page);
  await page.setViewportSize({ height: 900, width: 1440 });

  for (const route of publicRoutes) {
    await page.goto(route);
    await expect(page.locator("h1")).toBeVisible();
    await expectNoSeriousAxeFindings(page, route);
  }
});

test("staff routes fit representative desktop, tablet, and narrow widths", async ({ page }) => {
  await mockBrowserApis(page, "admin");

  for (const viewport of [viewports[0], viewports[2], viewports[4]]) {
    await page.setViewportSize(viewport);
    for (const route of adminRoutes) {
      await page.goto(route);
      await expect(page.locator("#staff-main-content")).toBeVisible();
      await expectNoPageOverflow(page, route, viewport.name);
    }
  }
});

test("staff accessibility, mobile navigation, and role boundaries", async ({ page }) => {
  await mockBrowserApis(page, "admin");
  await page.setViewportSize({ height: 900, width: 1440 });

  for (const route of adminRoutes) {
    await page.goto(route);
    await expect(page.locator("#staff-main-content")).toBeVisible();
    await expectNoSeriousAxeFindings(page, route);
  }

  await page.setViewportSize({ height: 720, width: 320 });
  await page.goto("/admin/workspace?panel=analytics");
  const menuButton = page.getByRole("button", { name: "Open navigation" });
  await menuButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#staff-navigation a[href]").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menuButton).toBeFocused();

  await page.unroute("**/*");
  await mockBrowserApis(page, "agent");
  await page.goto("/admin/automation");
  await expect(page).toHaveURL(/\/agent\/inbox$/);
});

test("owner and agent role variants preserve their route boundaries", async ({ page }) => {
  await mockBrowserApis(page, "owner");
  await page.setViewportSize({ height: 800, width: 1280 });
  await page.goto("/owner/inbox");
  await expect(page.locator("#staff-main-content")).toBeVisible();
  await expectNoPageOverflow(page, "/owner/inbox", "laptop");
  await expectNoSeriousAxeFindings(page, "/owner/inbox");
  await page.goto("/admin/workspace?panel=cs-api-settings");
  await expect(page).toHaveURL(/\/owner\/inbox$/);

  await page.unroute("**/*");
  await mockBrowserApis(page, "agent");
  await page.goto("/agent/inbox");
  await expect(page.locator("#staff-main-content")).toBeVisible();
  await expectNoPageOverflow(page, "/agent/inbox", "laptop");
  await expectNoSeriousAxeFindings(page, "/agent/inbox");
  await page.goto("/owner/automation");
  await expect(page).toHaveURL(/\/agent\/inbox$/);
});

test("chat dialog restores focus and honors reduced motion", async ({ page }) => {
  await mockBrowserApis(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/home");

  const closeButton = page.getByRole("button", { name: "Close chat" });
  await expect(closeButton).toBeVisible();
  await closeButton.click();
  const launcher = page.locator(".store-chat-launcher");
  await expect(launcher).toBeFocused();
  await launcher.click();
  await expect(closeButton).toBeFocused();

  const transitionDuration = await launcher.evaluate((element) => getComputedStyle(element).transitionDuration);
  expect(["0s", "0.01ms"]).toContain(transitionDuration);
});

test("a supported non-default chat color remains configurable and accessible", async ({ page }) => {
  await mockBrowserApis(page);
  await page.addInitScript(() => {
    localStorage.setItem("supportConsole_widgetConfig", JSON.stringify({
      accentColor: "#0044cc",
      behaviorVersion: 5,
      widgetWidth: 420
    }));
  });
  await page.goto("/home");
  await page.getByRole("button", { name: "Close chat" }).click();
  await expect(page.locator(".store-chat-launcher")).toHaveCSS("background-color", "rgb(0, 68, 204)");
  await expectNoSeriousAxeFindings(page, "/home with non-default widget color");
});
