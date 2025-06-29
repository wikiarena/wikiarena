import { WikipediaSearchService, WikipediaSearchResult } from './wikipedia-search.js';
import { WikipediaRandomService } from './wikipedia-random.js';

interface AutocompleteOptions {
    debounceMs?: number;
    minQueryLength?: number;
    placeholder?: string;
    onSelect?: (result: WikipediaSearchResult) => void;
    onValidationChange?: (isValid: boolean) => void;
}

class WikipediaAutocomplete {
    private input: HTMLInputElement;
    private container: HTMLElement;
    private dropdown: HTMLElement;
    private searchService: WikipediaSearchService;
    private randomService: WikipediaRandomService;
    private debounceTimer: number | null = null;
    private currentQuery: string = '';
    private results: WikipediaSearchResult[] = [];
    private selectedIndex: number = -1;
    private isOpen: boolean = false;
    private options: Required<AutocompleteOptions>;
    private randomCallback: ((title: string) => void) | null = null;

    constructor(input: HTMLInputElement, options: AutocompleteOptions = {}) {
        this.input = input;
        this.searchService = new WikipediaSearchService();
        this.randomService = new WikipediaRandomService();
        
        // Set default options
        this.options = {
            debounceMs: 300,
            minQueryLength: 2,
            placeholder: 'Search Wikipedia...',
            onSelect: () => {},
            onValidationChange: () => {},
            ...options
        };

        this.container = this.createContainer();
        this.dropdown = this.createDropdown();
        
        this.setupInput();
        this.setupEventListeners();
        this.startRandomCycling();
    }

    private createContainer(): HTMLElement {
        const container = document.createElement('div');
        container.className = 'wikipedia-autocomplete-container';
        
        // Insert container after the input
        this.input.parentNode?.insertBefore(container, this.input.nextSibling);
        container.appendChild(this.input);
        
        return container;
    }

    private createDropdown(): HTMLElement {
        const dropdown = document.createElement('div');
        dropdown.className = 'wikipedia-autocomplete-dropdown';
        dropdown.style.display = 'none';
        
        this.container.appendChild(dropdown);
        return dropdown;
    }

    private setupInput(): void {
        this.input.placeholder = this.options.placeholder;
        this.input.autocomplete = 'off';
        this.input.setAttribute('role', 'combobox');
        this.input.setAttribute('aria-expanded', 'false');
        this.input.setAttribute('aria-autocomplete', 'list');
    }

    private setupEventListeners(): void {
        // Input events
        this.input.addEventListener('input', this.handleInput.bind(this));
        this.input.addEventListener('keydown', this.handleKeydown.bind(this));
        this.input.addEventListener('focus', this.handleFocus.bind(this));
        this.input.addEventListener('blur', this.handleBlur.bind(this));

        // Global click to close dropdown
        document.addEventListener('click', this.handleDocumentClick.bind(this));
    }

    private handleInput(event: Event): void {
        const query = (event.target as HTMLInputElement).value;
        this.currentQuery = query;

        // Handle random cycling based on input state
        if (query.trim() === '') {
            this.startRandomCycling();
        } else {
            this.stopRandomCycling();
        }

        // Clear previous debounce
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        // Debounce the search
        this.debounceTimer = window.setTimeout(() => {
            this.performSearch(query);
        }, this.options.debounceMs);

        // Reset selection
        this.selectedIndex = -1;
    }

    private handleKeydown(event: KeyboardEvent): void {
        if (!this.isOpen || this.results.length === 0) {
            return;
        }

        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                this.selectedIndex = Math.min(this.selectedIndex + 1, this.results.length - 1);
                this.updateSelection();
                break;

            case 'ArrowUp':
                event.preventDefault();
                this.selectedIndex = Math.max(this.selectedIndex - 1, -1);
                this.updateSelection();
                break;

            case 'Enter':
                event.preventDefault();
                if (this.selectedIndex >= 0) {
                    this.selectResult(this.results[this.selectedIndex]);
                }
                break;

            case 'Escape':
                event.preventDefault();
                this.closeDropdown();
                break;

            case 'Tab':
                // Let tab close the dropdown but don't prevent default
                this.closeDropdown();
                break;
        }
    }

    private handleFocus(): void {
        if (this.currentQuery.length >= this.options.minQueryLength && this.results.length > 0) {
            this.openDropdown();
        }
    }

    private handleBlur(): void {
        // Delay closing to allow clicks on dropdown items
        setTimeout(() => {
            this.closeDropdown();
        }, 150);
    }

    private handleDocumentClick(event: Event): void {
        if (!this.container.contains(event.target as Node)) {
            this.closeDropdown();
        }
    }

    private async performSearch(query: string): Promise<void> {
        if (query.length < this.options.minQueryLength) {
            this.closeDropdown();
            this.results = [];
            return;
        }

        // Show loading state
        this.showLoading();

        try {
            const results = await this.searchService.search(query);
            
            // Only update if this is still the current query
            if (query === this.currentQuery) {
                this.results = results;
                this.renderResults();
                
                if (results.length > 0) {
                    this.openDropdown();
                } else {
                    this.showNoResults();
                }
            }
        } catch (error) {
            console.error('Search error:', error);
            this.showError();
        }
    }

    private showLoading(): void {
        this.dropdown.innerHTML = `
            <div class="wikipedia-autocomplete-loading">
                <div class="loading-spinner"></div>
                <span>Searching Wikipedia...</span>
            </div>
        `;
        this.openDropdown();
    }

    private showNoResults(): void {
        this.dropdown.innerHTML = `
            <div class="wikipedia-autocomplete-no-results">
                No Wikipedia pages found for "${this.escapeHtml(this.currentQuery)}"
            </div>
        `;
        this.openDropdown();
    }

    private showError(): void {
        this.dropdown.innerHTML = `
            <div class="wikipedia-autocomplete-error">
                Error searching Wikipedia. Please try again.
            </div>
        `;
        this.openDropdown();
    }

    private renderResults(): void {
        const html = this.results.map((result, index) => `
            <div class="wikipedia-autocomplete-item ${index === this.selectedIndex ? 'selected' : ''}" 
                 data-index="${index}"
                 role="option"
                 aria-selected="${index === this.selectedIndex}">
                <div class="item-title">${this.highlightQuery(result.title)}</div>
                ${result.description ? `<div class="item-description">${this.escapeHtml(result.description)}</div>` : ''}
            </div>
        `).join('');

        this.dropdown.innerHTML = html;

        // Add click listeners to items
        this.dropdown.querySelectorAll('.wikipedia-autocomplete-item').forEach((item, index) => {
            item.addEventListener('click', () => {
                this.selectResult(this.results[index]);
            });
        });
    }

    private updateSelection(): void {
        const items = this.dropdown.querySelectorAll('.wikipedia-autocomplete-item');
        
        items.forEach((item, index) => {
            const isSelected = index === this.selectedIndex;
            item.classList.toggle('selected', isSelected);
            item.setAttribute('aria-selected', isSelected.toString());
        });

        // Scroll selected item into view
        if (this.selectedIndex >= 0) {
            const selectedItem = items[this.selectedIndex] as HTMLElement;
            selectedItem?.scrollIntoView({ block: 'nearest' });
        }
    }

    private selectResult(result: WikipediaSearchResult): void {
        this.input.value = result.title;
        this.currentQuery = result.title;
        this.closeDropdown();
        
        // Trigger validation
        this.validateCurrentSelection();
        
        // Call onSelect callback
        this.options.onSelect(result);
    }

    private async validateCurrentSelection(): Promise<void> {
        const title = this.input.value.trim();
        if (!title) {
            this.options.onValidationChange(false);
            return;
        }

        try {
            const isValid = await this.searchService.validatePage(title);
            this.options.onValidationChange(isValid);
            
            // Add visual feedback
            this.input.classList.toggle('valid', isValid);
            this.input.classList.toggle('invalid', !isValid);
        } catch (error) {
            console.error('Validation error:', error);
            this.options.onValidationChange(false);
        }
    }

    private openDropdown(): void {
        this.isOpen = true;
        this.dropdown.style.display = 'block';
        this.input.setAttribute('aria-expanded', 'true');
    }

    private closeDropdown(): void {
        this.isOpen = false;
        this.dropdown.style.display = 'none';
        this.input.setAttribute('aria-expanded', 'false');
        this.selectedIndex = -1;
    }

    private highlightQuery(text: string): string {
        if (!this.currentQuery.trim()) return this.escapeHtml(text);
        
        const query = this.escapeHtml(this.currentQuery.trim());
        const escapedText = this.escapeHtml(text);
        const regex = new RegExp(`(${query})`, 'gi');
        
        return escapedText.replace(regex, '<mark>$1</mark>');
    }

    private escapeHtml(text: string): string {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Public methods
    public getValue(): string {
        return this.input.value;
    }

    public setValue(value: string): void {
        this.input.value = value;
        this.currentQuery = value;
        this.validateCurrentSelection();
    }

    public clear(): void {
        this.input.value = '';
        this.currentQuery = '';
        this.closeDropdown();
        this.results = [];
        this.startRandomCycling();
    }

    private startRandomCycling(): void {
        if (!this.randomCallback) {
            this.randomCallback = (title: string) => {
                // Only update placeholder if input is still empty
                if (this.input.value.trim() === '') {
                    this.input.placeholder = title;
                }
            };
        }
        this.randomService.startCycling(this.randomCallback, 200);
    }

    private stopRandomCycling(): void {
        if (this.randomCallback) {
            this.randomService.removeCallback(this.randomCallback);
        }
        // Reset to default placeholder
        this.input.placeholder = this.options.placeholder;
    }

    public destroy(): void {
        // Cancel any ongoing searches
        this.searchService.cancelCurrentSearch();
        
        // Stop random cycling
        this.stopRandomCycling();
        
        // Clear timers
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        // Remove event listeners
        document.removeEventListener('click', this.handleDocumentClick);
        
        // Remove DOM elements
        this.container.remove();
    }
}

export { WikipediaAutocomplete, type AutocompleteOptions }; 