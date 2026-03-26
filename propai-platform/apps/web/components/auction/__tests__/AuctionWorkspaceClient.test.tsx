import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuctionWorkspaceClient } from "@/components/auction/AuctionWorkspaceClient";
import { apiClient } from "@/lib/api-client";
import { renderWithQueryClient } from "@/test/render-with-query-client";

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;

    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
  apiClient: {
    getRuntimeConfig: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("AuctionWorkspaceClient", () => {
  it("renders live workspace data and runs auction analysis", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/auction/opportunities?limit=5") {
        return [
          {
            listing_id: "listing-001",
            case_number: "2026타경1001",
            court_name: "Seoul Central District Court",
            address: "Seoul Mapo-gu World Cup-ro 88",
            property_type: "mixed_use",
            minimum_bid_krw: 850000000,
            investment_score: 83,
            discount_ratio: 0.13,
            market_gap_ratio: 0.09,
            recommended_max_bid_krw: 930000000,
            expected_margin_krw: 145000000,
            diligence_flags: ["tenant-risk"],
          },
        ];
      }

      if (path === "/contractors/active?limit=6") {
        return [
          {
            contractor_id: "contractor-001",
            company_name: "Mapo Builders",
            category: "general_contractor",
            specialties: ["mep", "interior"],
            address: "Seoul",
            rating: 4.7,
          },
        ];
      }

      if (path === "/chatbot/sessions") {
        return [
          {
            session_id: "session-001",
            domain: "investment",
            title: "Auction advisory",
            message_count: 3,
            total_tokens: 1240,
            last_activity_at: "2026-03-22T00:00:00Z",
          },
        ];
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/auction/analyze") {
        return {
          listing_id: "listing-002",
          case_number: "2026타경2048",
          court_name: "Seoul Central District Court",
          address: "Seoul Seodaemun-gu Tongil-ro 11",
          property_type: "mixed_use",
          minimum_bid_krw: 910000000,
          investment_score: 91,
          discount_ratio: 0.17,
          market_gap_ratio: 0.12,
          recommended_max_bid_krw: 980000000,
          expected_margin_krw: 188000000,
          diligence_flags: ["lien-review", "repair-budget"],
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<AuctionWorkspaceClient locale="en" />);

    expect(await screen.findByText("Live auction workspace")).toBeInTheDocument();
    expect(await screen.findByText("2026타경1001")).toBeInTheDocument();
    expect(await screen.findByText("Mapo Builders")).toBeInTheDocument();
    expect(await screen.findByText("Auction advisory")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auction/analyze",
        expect.objectContaining({
          body: expect.any(Object),
        }),
      );
    });

    expect(await screen.findByText("2026타경2048")).toBeInTheDocument();
    expect(await screen.findByText(/Expected margin:/)).toBeInTheDocument();
  });

  it("renders query error cards and retries all read-side auction feeds", async () => {
    let failOpportunities = true;
    let failContractors = true;
    let failSessions = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/auction/opportunities?limit=5") {
        if (failOpportunities) {
          throw new Error("Auction opportunities feed unavailable");
        }

        return [
          {
            listing_id: "listing-retry-001",
            case_number: "2026타경3001",
            court_name: "Incheon District Court",
            address: "Incheon Yeonsu-gu 15",
            property_type: "office",
            minimum_bid_krw: 720000000,
            investment_score: 77,
            discount_ratio: 0.11,
            market_gap_ratio: 0.07,
            recommended_max_bid_krw: 760000000,
            expected_margin_krw: 102000000,
            diligence_flags: ["occupancy-review"],
          },
        ];
      }

      if (path === "/contractors/active?limit=6") {
        if (failContractors) {
          throw new Error("Contractor feed unavailable");
        }

        return [
          {
            contractor_id: "contractor-retry-001",
            company_name: "Recovered Contractors",
            category: "general_contractor",
            specialties: ["structure"],
            address: "Incheon",
            rating: 4.5,
          },
        ];
      }

      if (path === "/chatbot/sessions") {
        if (failSessions) {
          throw new Error("Session feed unavailable");
        }

        return [
          {
            session_id: "session-retry-001",
            domain: "investment",
            title: "Recovered advisory session",
            message_count: 1,
            total_tokens: 420,
            last_activity_at: "2026-03-22T00:00:00Z",
          },
        ];
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(<AuctionWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Auction opportunities unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Auction opportunities feed unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Contractor network unavailable"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Contractor feed unavailable")).toBeInTheDocument();
    expect(
      await screen.findByText("Chatbot sessions unavailable"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Session feed unavailable")).toBeInTheDocument();

    failOpportunities = false;
    failContractors = false;
    failSessions = false;

    const retryButtons = await screen.findAllByRole("button", { name: "Retry" });
    await userEvent.click(retryButtons[0]);
    await userEvent.click(retryButtons[1]);
    await userEvent.click(retryButtons[2]);

    expect(await screen.findByText("2026타경3001")).toBeInTheDocument();
    expect(await screen.findByText("Recovered Contractors")).toBeInTheDocument();
    expect(
      await screen.findByText("Recovered advisory session"),
    ).toBeInTheDocument();
  });
});
