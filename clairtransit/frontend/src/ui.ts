import { ApiError, type EditionBrief } from "./api";

export type EditionOption = EditionBrief & { warning: string | null };

export function errorText(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  if (err.code === "REVISION_CONFLICT")
    return "Quelqu'un a modifié cet élément depuis votre ouverture. Rechargez pour voir sa version ; rien n'a été écrasé.";
  return err.message;
}
