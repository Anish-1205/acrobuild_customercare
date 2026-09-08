import { createContext, useContext, useState, ReactNode } from "react";

export interface TicketSearchSuggestion {
  id: string;
  kind: "customer" | "email" | "ticket" | "topic";
  primary: string;
  secondary: string;
  searchText: string;
  value: string;
}

interface SearchContextType {
  searchSuggestions: TicketSearchSuggestion[];
  setSearchSuggestions: (suggestions: TicketSearchSuggestion[]) => void;
  ticketSearchQuery: string;
  setTicketSearchQuery: (query: string) => void;
  visibleTicketCount: number;
  setVisibleTicketCount: (count: number) => void;
}

const SearchContext = createContext<SearchContextType | undefined>(undefined);

export function SearchProvider({ children }: { children: ReactNode }) {
  const [searchSuggestions, setSearchSuggestions] = useState<TicketSearchSuggestion[]>([]);
  const [ticketSearchQuery, setTicketSearchQuery] = useState("");
  const [visibleTicketCount, setVisibleTicketCount] = useState(0);

  return (
    <SearchContext.Provider
      value={{
        searchSuggestions,
        setSearchSuggestions,
        ticketSearchQuery,
        setTicketSearchQuery,
        visibleTicketCount,
        setVisibleTicketCount
      }}
    >
      {children}
    </SearchContext.Provider>
  );
}

export function useSearch() {
  const context = useContext(SearchContext);
  if (!context) {
    throw new Error("useSearch must be used within SearchProvider");
  }
  return context;
}
