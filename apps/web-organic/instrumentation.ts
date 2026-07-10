export { onRequestError } from "@agri/observability/server";

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { registerSentry } = await import("@agri/observability/server");
    await registerSentry();
  }
}
