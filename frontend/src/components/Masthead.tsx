import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import './Masthead.css';
import { searchTickers } from '../api';
import type { TickerSuggestion } from '../types';
import { useDebouncedValue } from '../useDebouncedValue';

interface MastheadProps {
  onSearch: (ticker: string) => void;
  isLoading: boolean;
}

export function Masthead({ onSearch, isLoading }: MastheadProps) {
  const [value, setValue] = useState('');
  const [suggestions, setSuggestions] = useState<TickerSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const debouncedValue = useDebouncedValue(value, 250);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const trimmed = debouncedValue.trim();
    if (trimmed.length < 1) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    searchTickers(trimmed).then((res) => {
      if (!cancelled) setSuggestions(res.results);
    });
    return () => {
      cancelled = true;
    };
  }, [debouncedValue]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function selectTicker(symbol: string) {
    setValue(symbol);
    setSuggestions([]);
    setShowSuggestions(false);
    setHighlightedIndex(-1);
    onSearch(symbol.toUpperCase());
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (highlightedIndex >= 0 && suggestions[highlightedIndex]) {
      selectTicker(suggestions[highlightedIndex].symbol);
      return;
    }
    const trimmed = value.trim().toUpperCase();
    if (trimmed) {
      setShowSuggestions(false);
      onSearch(trimmed);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!showSuggestions || suggestions.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Escape') {
      setShowSuggestions(false);
    }
  }

  return (
    <header className="masthead">
      <div className="masthead__inner">
        <div className="masthead__brand">
          <h1 className="masthead__title">Valuation Lab</h1>
          <p className="masthead__tagline">Type a ticker or company name. See what it is actually worth.</p>
        </div>

        <div className="masthead__search-container" ref={containerRef}>
          <form className="masthead__search" onSubmit={handleSubmit} autoComplete="off">
            <input
              className="masthead__input mono"
              type="text"
              placeholder="Apple, AAPL, Novo Nordisk…"
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                setShowSuggestions(true);
                setHighlightedIndex(-1);
              }}
              onFocus={() => setShowSuggestions(true)}
              onKeyDown={handleKeyDown}
              aria-label="Stock ticker or company name"
              aria-autocomplete="list"
              spellCheck={false}
            />
            <button className="masthead__button" type="submit" disabled={isLoading || !value.trim()}>
              {isLoading ? 'Valuing…' : 'Value it'}
            </button>
          </form>

          {showSuggestions && suggestions.length > 0 && (
            <ul className="masthead__suggestions" role="listbox">
              {suggestions.map((s, i) => (
                <li key={s.symbol}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={i === highlightedIndex}
                    className={`masthead__suggestion ${i === highlightedIndex ? 'masthead__suggestion--active' : ''}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectTicker(s.symbol)}
                  >
                    <span className="mono masthead__suggestion-symbol">{s.symbol}</span>
                    <span className="masthead__suggestion-name">{s.name}</span>
                    {s.exchange && <span className="masthead__suggestion-exchange">{s.exchange}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </header>
  );
}
