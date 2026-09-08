export type WidgetConfig = {
  accentColor: string;
  aiResponsesEnabled: boolean;
  articleSuggestionsEnabled: boolean;
  assistantName: string;
  behaviorVersion?: number;
  chatTitle: string;
  fontFamily: string;
  introMessage: string;
  launcherLabel: string;
  launcherWidth: number;
  logoUrl: string;
  widgetKey: string;
  widgetWidth: number;
};

const WIDGET_CONFIG_STORAGE_KEY = "supportConsole_widgetConfig";
const legacyFontFamily = "Aptos";
const defaultWidgetFont = "Inter, ui-sans-serif, system-ui, sans-serif";
const legacyIntroMessages = [
  "Pick a support topic to open the matching support article. If you still need help, we will collect your email and message for a ticket.",
  "Pick a support topic to open the matching article. If you still need help, we will collect your email and message for a ticket.",
  "Welcome! Please enter your email and send us a message to connect with our team."
];
const defaultIntroMessage =
  "Welcome to Acrobuild support. Share your project, property, or construction question and our team will take it from there.";
const currentBehaviorVersion = 5;

export const defaultWidgetConfig: WidgetConfig = {
  accentColor: "#1f2937",
  aiResponsesEnabled: true,
  articleSuggestionsEnabled: true,
  assistantName: "Acrobuild support",
  behaviorVersion: currentBehaviorVersion,
  chatTitle: "Need help with your project?",
  fontFamily: defaultWidgetFont,
  introMessage: defaultIntroMessage,
  launcherLabel: "Open support chat",
  launcherWidth: 60,
  logoUrl: "",
  widgetKey: "acrobuild-widget-v4",
  widgetWidth: 340
};

export function loadWidgetConfig() {
  if (typeof window === "undefined") {
    return defaultWidgetConfig;
  }

  try {
    const rawConfig = window.localStorage.getItem(WIDGET_CONFIG_STORAGE_KEY);

    if (!rawConfig) {
      return defaultWidgetConfig;
    }

    const parsedConfig = JSON.parse(rawConfig) as Partial<WidgetConfig>;
    const previousVersion = parsedConfig.behaviorVersion ?? 0;
    const shouldRefreshLegacyBranding = previousVersion < currentBehaviorVersion;

    return {
      ...defaultWidgetConfig,
      ...parsedConfig,
      aiResponsesEnabled:
        previousVersion >= 2
          ? (parsedConfig.aiResponsesEnabled ?? defaultWidgetConfig.aiResponsesEnabled)
          : defaultWidgetConfig.aiResponsesEnabled,
      assistantName: shouldRefreshLegacyBranding
        ? defaultWidgetConfig.assistantName
        : (parsedConfig.assistantName ?? defaultWidgetConfig.assistantName),
      behaviorVersion: currentBehaviorVersion,
      chatTitle: shouldRefreshLegacyBranding
        ? defaultWidgetConfig.chatTitle
        : (parsedConfig.chatTitle ?? defaultWidgetConfig.chatTitle),
      fontFamily:
        shouldRefreshLegacyBranding || parsedConfig.fontFamily === legacyFontFamily
          ? defaultWidgetConfig.fontFamily
          : (parsedConfig.fontFamily ?? defaultWidgetConfig.fontFamily),
      introMessage:
        legacyIntroMessages.includes(parsedConfig.introMessage ?? "") || shouldRefreshLegacyBranding
          ? defaultIntroMessage
          : (parsedConfig.introMessage ?? defaultWidgetConfig.introMessage),
      widgetKey: shouldRefreshLegacyBranding
        ? defaultWidgetConfig.widgetKey
        : (parsedConfig.widgetKey ?? defaultWidgetConfig.widgetKey)
    };
  } catch {
    return defaultWidgetConfig;
  }
}

export function saveWidgetConfig(config: WidgetConfig) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(
    WIDGET_CONFIG_STORAGE_KEY,
    JSON.stringify({
      ...config,
      behaviorVersion: currentBehaviorVersion
    })
  );
}

export function buildInstallSnippet(
  widgetKey: string,
  accentColor: string,
  width: number,
  logoUrl?: string
) {
  const snippetLines = [
    "<!-- Customer Support Agent Widget Start -->",
    `<script id="customer-support-widget"`,
    `  src="https://config.support-agent.chat/widget-loader/${widgetKey}"`,
    `  data-accent="${accentColor}"`,
    `  data-widget-width="${width}"`,
    ...(logoUrl?.trim() ? [`  data-logo="${logoUrl.trim()}"`] : []),
    `  async></script>`,
    "<!-- Customer Support Agent Widget End -->"
  ];

  return snippetLines.join("\n");
}