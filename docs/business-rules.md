# Scope and business rules

## MVP

One city and long-term apartment rentals. Before implementation, the team must select the city, currency, treatment of utility costs, and permitted sources.

Flow: collection → normalization → deduplication → geographic enrichment → valuation → signals → API → interface → manual review.

## Valuation

- Baseline: median price per square meter for comparable properties, considering the period, neighborhood, and property characteristics.
- Compare ML and baseline results on the same test set.
- Validate prediction intervals using observed coverage on held-out data.
- Statuses: `within_range`, `above_range`, `below_range`, `insufficient_data`.
- Abstain from confident valuation when comparable data is insufficient; determine thresholds through evaluation.
- The market index represents asking prices, not signed rental agreements.

## Risk signals

Signals may include price anomalies, address/coordinate inconsistencies, conflicting duplicates, and explicit demands for payment before a viewing. Each signal records its rule, evidence, timestamp, and version. Price alone is not evidence of fraud.

## Ontology

Entities: Property, Listing, Building, District, City, InfrastructureObject, Estimate, RiskSignal, Review.

Relationships: describes, locatedIn, near, estimatedBy, hasSignal.

Rules establish geographic proximity; market data validates its effect on price. Confirm the ontology format and OWL/RDF requirements against course assessment criteria.

## Data lifecycle

- Listings and physical properties are separate entities.
- Preserve price history.
- Mark obsolete listings as inactive.
- Collection failures must not imply that listings have been removed.
- Repeated collection must not create duplicate observations.
- Refresh market data weekly; evaluate available data on demand.
- Keep model retraining separate from collection.

## Evaluation

Split data by time and keep duplicate groups from crossing training/test boundaries. Metrics include MAE, median absolute error, interval coverage and width, neighborhood-level results, and the abstention rate. Evaluate risk rules on labeled examples; do not claim fraud detection accuracy without ground-truth labels.
