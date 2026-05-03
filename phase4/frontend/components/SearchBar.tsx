"use client";

import { useState } from "react";

type Props = {
  initialQuery?: string;
  onSubmit: (query: string) => void;
  isLoading?: boolean;
};

export default function SearchBar({ initialQuery = "", onSubmit, isLoading }: Props) {
  const [value, setValue] = useState(initialQuery);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(value.trim());
      }}
      className="flex w-full items-center gap-2 rounded-2xl bg-white p-2 shadow-sm ring-1 ring-slate-200 focus-within:ring-2 focus-within:ring-accent"
    >
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder='Try "wireless earbuds under 2000" or "skincare for oily skin"'
        className="w-full bg-transparent px-3 py-2 text-base placeholder:text-slate-400 focus:outline-none"
        aria-label="Search products"
      />
      <button
        type="submit"
        disabled={isLoading}
        className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isLoading ? "Searching…" : "Search"}
      </button>
    </form>
  );
}
