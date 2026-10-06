import type { SupportAssistResponse } from "../types";
import {
  getSupportAssist,
  streamSupportAssist,
  type SupportAssistRequest
} from "./api";

export type SupportAssistTransportHandlers = {
  onDelta?: (text: string) => void;
  onDone: (response: SupportAssistResponse) => void;
  onPartial: (answer: string) => void;
};

export async function requestSupportAssist(
  payload: SupportAssistRequest,
  handlers: SupportAssistTransportHandlers
): Promise<"json" | "partial" | "stream"> {
  let streamedAnswer = "";
  let streamReportedError = false;
  try {
    await streamSupportAssist(payload, {
      onDelta: (text) => {
        streamedAnswer += text;
        handlers.onDelta?.(text);
      },
      onDone: handlers.onDone,
      onError: () => {
        streamReportedError = true;
      }
    });
    if (streamReportedError) throw new Error("The support stream reported an error.");
    return "stream";
  } catch {
    if (streamedAnswer.trim()) {
      handlers.onPartial(streamedAnswer.trim());
      return "partial";
    }
  }

  const response = await getSupportAssist(payload);
  handlers.onDone(response);
  return "json";
}
