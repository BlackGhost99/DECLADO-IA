import { describe, expect, it } from "vitest";
import type { Revision } from "../src/api";
import { caseSteps } from "../src/ui";

function rev(state: string, extra: Partial<Revision> = {}): Revision {
  return {
    state, state_label: state,
    documents: [{ id: "d", replaced_by_id: null }],
    invoices: [{ lines: [{}] }],
    goods_lines: [{ decision: { is_current: true } }],
    decisions: [],
    export_count: 0,
    ...extra,
  } as unknown as Revision;
}
const states = (r: Revision) => Object.fromEntries(caseSteps(r).map((s) => [s.key, s.state]));
const submitted = (calculated: boolean) => ({ kind: "submitted", calculated }) as Revision["decisions"] extends (infer D)[] | undefined ? D : never;

describe("Étapes du dossier", () => {
  it("le calcul est l'étape en cours tant qu'il n'est pas soumis", () => {
    expect(states(rev("in_preparation"))).toMatchObject({ marchandises: "done", calculs: "current", validation: "todo", export: "todo" });
  });

  it("un calcul complet soumis puis validé coche le calcul ; l'export se coche une fois un fichier généré", () => {
    const validated = rev("validated", { decisions: [submitted(true)] });
    expect(states(validated)).toMatchObject({ calculs: "done", validation: "done", export: "current" });
    expect(states({ ...validated, export_count: 2 })).toMatchObject({ export: "done" });
  });

  it("un calcul incomplet soumis (consultation) ne compte pas comme fait", () => {
    expect(states(rev("to_validate", { decisions: [submitted(false)] }))).toMatchObject({ calculs: "current" });
  });
});
