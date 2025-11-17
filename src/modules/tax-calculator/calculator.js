/**
 * Calculateur de taxes et droits de douane pour la zone CEMAC
 * 
 * Réglementation CEMAC:
 * - Droits de douane (DD): Variable selon le tarif douanier (5%, 10%, 20%, 30%)
 * - TVA: 19.25% sur (Valeur CIF + DD)
 * - Taxe Communautaire d'Intégration (TCI): 1% sur la valeur CIF
 * - Redevance Statistique: 1% sur la valeur CIF
 * 
 * Valeur CIF = Valeur FOB + Fret + Assurance
 */
class TaxCalculator {
    constructor() {
        // Taux de taxes applicables dans la zone CEMAC
        this.taxRates = {
            customsDuty: {
                // Taux variables selon la classification tarifaire
                category1: 0.05,  // 5% - Biens de première nécessité
                category2: 0.10,  // 10% - Biens intermédiaires
                category3: 0.20,  // 20% - Biens de consommation
                category4: 0.30   // 30% - Biens de luxe
            },
            vat: 0.1925,          // 19.25% - TVA
            tci: 0.01,            // 1% - Taxe Communautaire d'Intégration
            statisticalFee: 0.01, // 1% - Redevance Statistique
            ohada: 0.005          // 0.5% - Contribution OHADA (optionnel)
        };

        // Classification HS par catégorie
        this.hsCategories = {
            '8471': 'category3', // Matériel informatique - 20%
            '9403': 'category3', // Meubles - 20%
            '0101': 'category1', // Produits agricoles - 5%
            '8703': 'category4', // Véhicules - 30%
        };
    }

    /**
     * Calcule toutes les taxes et droits de douane
     * @param {Object} invoiceData - Données de la facture commerciale
     * @param {Object} transportData - Données de transport (optionnel)
     * @param {Object} insuranceData - Données d'assurance (optionnel)
     * @returns {Object} - Détail des taxes calculées
     */
    calculate(invoiceData, transportData = null, insuranceData = null) {
        // 1. Calculer la valeur FOB
        const fobValue = this.calculateFOB(invoiceData);

        // 2. Calculer les frais de transport
        const freight = transportData ? this.calculateFreight(transportData) : 0;

        // 3. Calculer l'assurance
        const insurance = insuranceData ? this.calculateInsurance(insuranceData) : 0;

        // 4. Calculer la valeur CIF (Cost, Insurance, Freight)
        const cifValue = fobValue + freight + insurance;

        // 5. Déterminer le taux de droits de douane applicable
        const customsDutyRate = this.determineCustomsDutyRate(invoiceData);

        // 6. Calculer les droits de douane
        const customsDuty = cifValue * customsDutyRate;

        // 7. Calculer la base taxable pour la TVA (CIF + DD)
        const vatBase = cifValue + customsDuty;

        // 8. Calculer la TVA
        const vat = vatBase * this.taxRates.vat;

        // 9. Calculer la TCI (Taxe Communautaire d'Intégration)
        const tci = cifValue * this.taxRates.tci;

        // 10. Calculer la redevance statistique
        const statisticalFee = cifValue * this.taxRates.statisticalFee;

        // 11. Calculer le total à payer
        const total = customsDuty + vat + tci + statisticalFee;

        return {
            // Valeurs de base
            fobValue: Math.round(fobValue),
            freight: Math.round(freight),
            insurance: Math.round(insurance),
            cifValue: Math.round(cifValue),

            // Taxes et droits
            customsDuty: Math.round(customsDuty),
            customsDutyRate: customsDutyRate * 100, // En pourcentage
            vat: Math.round(vat),
            vatRate: this.taxRates.vat * 100,
            tci: Math.round(tci),
            tciRate: this.taxRates.tci * 100,
            statisticalFee: Math.round(statisticalFee),
            statisticalFeeRate: this.taxRates.statisticalFee * 100,

            // Total
            total: Math.round(total),

            // Détails supplémentaires
            calculationDate: new Date().toISOString(),
            currency: 'XAF',
            breakdown: this.generateBreakdown(cifValue, customsDuty, vat, tci, statisticalFee)
        };
    }

    /**
     * Calcule la valeur FOB à partir de la facture
     */
    calculateFOB(invoiceData) {
        if (invoiceData.articles && Array.isArray(invoiceData.articles)) {
            return invoiceData.articles.reduce((total, article) => {
                return total + (article.montantTotal || 0);
            }, 0);
        }
        return invoiceData.montantTotal || 0;
    }

    /**
     * Calcule les frais de transport
     */
    calculateFreight(transportData) {
        return transportData.montantTotal || 0;
    }

    /**
     * Calcule les frais d'assurance
     */
    calculateInsurance(insuranceData) {
        return insuranceData.primeAssurance || 0;
    }

    /**
     * Détermine le taux de droits de douane applicable
     */
    determineCustomsDutyRate(invoiceData) {
        if (!invoiceData.articles || invoiceData.articles.length === 0) {
            return this.taxRates.customsDuty.category2; // Taux par défaut 10%
        }

        // Utiliser le code HS du premier article pour déterminer la catégorie
        const firstArticle = invoiceData.articles[0];
        const hsCode = firstArticle.codeHS;

        if (hsCode) {
            // Extraire les 4 premiers chiffres du code HS
            const hsPrefix = hsCode.substring(0, 4);
            const category = this.hsCategories[hsPrefix] || 'category2';
            return this.taxRates.customsDuty[category];
        }

        return this.taxRates.customsDuty.category2; // Taux par défaut 10%
    }

    /**
     * Génère un détail du calcul
     */
    generateBreakdown(cifValue, customsDuty, vat, tci, statisticalFee) {
        return [
            {
                label: 'Valeur CIF',
                amount: Math.round(cifValue),
                percentage: 100
            },
            {
                label: 'Droits de Douane',
                amount: Math.round(customsDuty),
                percentage: Math.round((customsDuty / cifValue) * 100 * 100) / 100
            },
            {
                label: 'TVA',
                amount: Math.round(vat),
                percentage: Math.round((vat / cifValue) * 100 * 100) / 100
            },
            {
                label: 'TCI',
                amount: Math.round(tci),
                percentage: Math.round((tci / cifValue) * 100 * 100) / 100
            },
            {
                label: 'Redevance Statistique',
                amount: Math.round(statisticalFee),
                percentage: Math.round((statisticalFee / cifValue) * 100 * 100) / 100
            },
            {
                label: 'Total des Taxes',
                amount: Math.round(customsDuty + vat + tci + statisticalFee),
                percentage: Math.round(((customsDuty + vat + tci + statisticalFee) / cifValue) * 100 * 100) / 100
            }
        ];
    }

    /**
     * Calcule les taxes pour plusieurs articles avec des codes HS différents
     */
    calculateDetailedByArticle(invoiceData, transportData = null, insuranceData = null) {
        const results = [];
        
        if (!invoiceData.articles || invoiceData.articles.length === 0) {
            return results;
        }

        // Calculer les frais proportionnels pour chaque article
        const totalFOB = this.calculateFOB(invoiceData);
        const totalFreight = transportData ? this.calculateFreight(transportData) : 0;
        const totalInsurance = insuranceData ? this.calculateInsurance(insuranceData) : 0;

        for (const article of invoiceData.articles) {
            const articleFOB = article.montantTotal || 0;
            const proportion = articleFOB / totalFOB;

            const articleFreight = totalFreight * proportion;
            const articleInsurance = totalInsurance * proportion;
            const articleCIF = articleFOB + articleFreight + articleInsurance;

            // Déterminer le taux de DD pour cet article
            const hsPrefix = article.codeHS ? article.codeHS.substring(0, 4) : null;
            const category = hsPrefix ? (this.hsCategories[hsPrefix] || 'category2') : 'category2';
            const customsDutyRate = this.taxRates.customsDuty[category];

            const customsDuty = articleCIF * customsDutyRate;
            const vatBase = articleCIF + customsDuty;
            const vat = vatBase * this.taxRates.vat;
            const tci = articleCIF * this.taxRates.tci;
            const statisticalFee = articleCIF * this.taxRates.statisticalFee;

            results.push({
                article: article.description,
                codeHS: article.codeHS,
                quantite: article.quantite,
                fobValue: Math.round(articleFOB),
                cifValue: Math.round(articleCIF),
                customsDuty: Math.round(customsDuty),
                vat: Math.round(vat),
                tci: Math.round(tci),
                statisticalFee: Math.round(statisticalFee),
                total: Math.round(customsDuty + vat + tci + statisticalFee)
            });
        }

        return results;
    }
}

module.exports = TaxCalculator;
