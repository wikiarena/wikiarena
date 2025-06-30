interface ModelInfo {
    provider: string;
    input_cost_per_1m_tokens: number;
    output_cost_per_1m_tokens: number;
    default_settings: {
        max_tokens: number;
    };
}

interface ModelOption {
    id: string;
    provider: string;
    inputCost: number;
    outputCost: number;
    maxTokens: number;
    iconPath: string;
}

interface ModelSelectorOptions {
    placeholder?: string;
    onSelect?: (model: ModelOption) => void;
    onValidationChange?: (isValid: boolean) => void;
}

class ModelSelector {
    private input: HTMLInputElement;
    private container: HTMLElement;
    private dropdown: HTMLElement;
    private models: ModelOption[] = [];
    private filteredModels: ModelOption[] = [];
    private selectedIndex: number = -1;
    private isOpen: boolean = false;
    private options: Required<ModelSelectorOptions>;
    private currentQuery: string = '';
    private selectedModel: ModelOption | null = null;

    constructor(input: HTMLInputElement, options: ModelSelectorOptions = {}) {
        this.input = input;
        
        // Set default options
        this.options = {
            placeholder: 'Search for a model...',
            onSelect: () => {},
            onValidationChange: () => {},
            ...options
        };

        this.container = this.createContainer();
        this.dropdown = this.createDropdown();
        
        this.setupInput();
        this.setupEventListeners();
        this.loadModels();
    }

    private createContainer(): HTMLElement {
        const container = document.createElement('div');
        container.className = 'model-selector-container';
        
        // Insert container after the input
        this.input.parentNode?.insertBefore(container, this.input.nextSibling);
        container.appendChild(this.input);
        
        return container;
    }

    private createDropdown(): HTMLElement {
        const dropdown = document.createElement('div');
        dropdown.className = 'model-selector-dropdown';
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
        this.input.readOnly = true; // Make it click-to-open only
    }

    private setupEventListeners(): void {
        // Input events
        this.input.addEventListener('click', this.handleInputClick.bind(this));
        this.input.addEventListener('keydown', this.handleKeydown.bind(this));
        this.input.addEventListener('focus', this.handleFocus.bind(this));
        this.input.addEventListener('blur', this.handleBlur.bind(this));

        // Global click to close dropdown
        document.addEventListener('click', this.handleDocumentClick.bind(this));
    }

    private async loadModels(): Promise<void> {
        try {
            const response = await fetch('./models.json');
            const modelsData: Record<string, ModelInfo> = await response.json();
            
            this.models = Object.entries(modelsData).map(([id, info]) => ({
                id,
                provider: info.provider,
                inputCost: info.input_cost_per_1m_tokens,
                outputCost: info.output_cost_per_1m_tokens,
                maxTokens: info.default_settings.max_tokens,
                iconPath: this.getProviderIcon(info.provider)
            }));

            this.filteredModels = [...this.models];
        } catch (error) {
            console.error('Failed to load models:', error);
        }
    }



    private getProviderIcon(provider: string): string {
        const iconMap: Record<string, string> = {
            'anthropic': './assets/icons/claude-color.svg',
            'openai': './assets/icons/openai.svg',
            'google': './assets/icons/gemini-color.svg',
            'meta': './assets/icons/meta-color.svg',
            'random': './assets/icons/dice.svg'
        };

        return iconMap[provider] || './assets/icons/question-mark.svg';
    }

    private handleInputClick(): void {
        if (this.isOpen) {
            this.closeDropdown();
        } else {
            this.openDropdown();
        }
    }

    private handleKeydown(event: KeyboardEvent): void {
        if (!this.isOpen || this.filteredModels.length === 0) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                this.openDropdown();
            }
            return;
        }

        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                this.selectedIndex = Math.min(this.selectedIndex + 1, this.filteredModels.length - 1);
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
                    this.selectModel(this.filteredModels[this.selectedIndex]);
                }
                break;

            case 'Escape':
                event.preventDefault();
                this.closeDropdown();
                break;

            case 'Tab':
                this.closeDropdown();
                break;
        }
    }

    private handleFocus(): void {
        // Focus doesn't automatically open dropdown - only click does
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

    private filterModels(query: string): void {
        const lowercaseQuery = query.toLowerCase();
        this.filteredModels = this.models.filter(model => 
            model.id.toLowerCase().includes(lowercaseQuery) ||
            model.provider.toLowerCase().includes(lowercaseQuery)
        );
        this.selectedIndex = -1;
    }

    private renderModels(): void {
        if (this.filteredModels.length === 0) {
            this.dropdown.innerHTML = `
                <div class="model-selector-no-results">
                    No models found
                </div>
            `;
            return;
        }

        const html = this.filteredModels.map((model, index) => `
            <div class="model-selector-item ${index === this.selectedIndex ? 'selected' : ''}" 
                 data-index="${index}"
                 role="option"
                 aria-selected="${index === this.selectedIndex}">
                <div class="model-selector-item-icon">
                    <img src="${model.iconPath}" alt="${model.provider}" />
                </div>
                <div class="model-selector-item-content">
                    <div class="model-selector-item-name">${this.escapeHtml(model.id)}</div>
                    <div class="model-selector-item-details">
                        <span class="model-selector-cost">$${model.inputCost.toFixed(2)}/${model.outputCost.toFixed(2)} per 1M tokens</span>
                    </div>
                </div>
            </div>
        `).join('');

        this.dropdown.innerHTML = html;

        // Add click listeners to items
        this.dropdown.querySelectorAll('.model-selector-item').forEach((item, index) => {
            item.addEventListener('click', () => {
                this.selectModel(this.filteredModels[index]);
            });
        });
    }

    private updateSelection(): void {
        const items = this.dropdown.querySelectorAll('.model-selector-item');
        
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

    private selectModel(model: ModelOption): void {
        this.selectedModel = model;
        this.input.value = model.id;
        this.closeDropdown();
        
        // Add visual feedback
        this.input.classList.add('valid');
        this.input.classList.remove('invalid');
        
        // Call callbacks
        this.options.onSelect(model);
        this.options.onValidationChange(true);
    }

    private openDropdown(): void {
        // Reset filter to show all models when opening
        this.currentQuery = '';
        this.filteredModels = [...this.models];
        this.selectedIndex = -1;
        
        this.renderModels();
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

    private escapeHtml(text: string): string {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }



    // Public methods
    public getValue(): string {
        return this.selectedModel?.id || '';
    }

    public getSelectedModel(): ModelOption | null {
        return this.selectedModel;
    }

    public setValue(modelId: string): void {
        const model = this.models.find(m => m.id === modelId);
        if (model) {
            this.selectModel(model);
        }
    }

    public clear(): void {
        this.selectedModel = null;
        this.input.value = '';
        this.input.classList.remove('valid', 'invalid');
        this.closeDropdown();
        this.options.onValidationChange(false);
    }

    public destroy(): void {
        // Remove event listeners
        document.removeEventListener('click', this.handleDocumentClick);
        
        // Remove DOM elements
        this.container.remove();
    }
}

export { ModelSelector, type ModelSelectorOptions, type ModelOption }; 