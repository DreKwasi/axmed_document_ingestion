import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.vue";

const api = vi.hoisted(() => ({
  fetchEvaluations: vi.fn(),
  runEvaluation: vi.fn(),
  uploadDocument: vi.fn(),
  confirmMapping: vi.fn()
}));

vi.mock("@/api", () => ({
  ...api
}));

describe("App", () => {
  beforeEach(() => {
    api.fetchEvaluations.mockResolvedValue({
      cases: [
        {
          id: "sanova-schema-reuse-v1",
          title: "Sanova ERP schema learns once and reuses deterministically",
          rubric: [
            {
              id: "canonical_fidelity",
              label: "Canonical fidelity",
              success_criterion: "Critical quotation fields match ground truth."
            }
          ]
        }
      ],
      runs: []
    });
  });

  it("shows the SQLite-backed evaluation lab and persists a requested run through the API", async () => {
    api.runEvaluation.mockResolvedValue({ id: "run-1", status: "completed" });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Evaluation lab")?.trigger("click");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Evaluation lab");
    expect(wrapper.text()).toContain("Canonical fidelity");
    expect(api.runEvaluation).toHaveBeenCalledOnce();
    expect(api.fetchEvaluations).toHaveBeenCalledTimes(2);
  });

  it("shows the human mapping checkpoint for a newly observed schema and confirms it", async () => {
    api.uploadDocument.mockResolvedValue({
      id: "document-1",
      filename: "sanova.json",
      status: "needs_mapping_confirmation",
      source_system: "SanovaERP",
      schema_version: "2.4.1",
      semantic_mapping_calls: 1,
      mapping: { id: "mapping-1", trust_state: "proposed", times_seen: 1, times_confirmed: 0, human_verified: false },
      quotation: { line_items: [], supplier: {}, commercial_terms: {} }
    });
    api.confirmMapping.mockResolvedValue({
      id: "document-1",
      filename: "sanova.json",
      status: "needs_review",
      source_system: "SanovaERP",
      schema_version: "2.4.1",
      semantic_mapping_calls: 1,
      mapping: { id: "mapping-1", trust_state: "trusted", times_seen: 1, times_confirmed: 1, human_verified: true },
      quotation: { line_items: [], supplier: {}, commercial_terms: {} }
    });
    const wrapper = mount(App);
    await flushPromises();

    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", {
      value: [new File(["{}"], "sanova.json", { type: "application/json" })]
    });
    await input.trigger("change");
    await flushPromises();

    expect(wrapper.text()).toContain("Confirm this source-to-canonical map");
    expect(wrapper.text()).toContain("Semantic calls1");
    await wrapper.get(".confirmation-panel .primary-action").trigger("click");
    await flushPromises();
    expect(api.confirmMapping).toHaveBeenCalledWith("document-1");
    expect(wrapper.text()).toContain("Ready for quotation review");
  });
});
