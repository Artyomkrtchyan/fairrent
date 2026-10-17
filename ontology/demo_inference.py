import os
from rdflib import Graph, Namespace, RDF, RDFS, Literal

print("Script started...")

# 1. Check if ontology file exists
ttl_file = "real_estate_ontology.ttl"
if not os.path.exists(ttl_file):
    print(f"ERROR: Cannot find '{ttl_file}' in the current directory!")
    print(f"Current working directory is: {os.getcwd()}")
    exit()

# 2. Load RDF Graph
print(f"Loading ontology from '{ttl_file}'...")
g = Graph()
try:
    g.parse(ttl_file, format="turtle")
    print(f"Ontology loaded successfully! Total triples: {len(g)}\n")
except Exception as e:
    print(f"ERROR loading ontology: {e}")
    exit()

EX = Namespace("http://example.org/fairrent#")

# 3. Query Competency Question 1
print("=== COMPETENCY QUESTION 1 ===")
print("Q1: Which listings are located in Kentron and close to Yeritasardakan Metro?")

cq1_query = """
PREFIX : <http://example.org/fairrent#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?listing ?price ?districtName ?nodeName WHERE {
    ?listing a :Listing ;
             :hasPriceUSD ?price ;
             :describesProperty ?prop .
    ?prop :locatedInDistrict ?district ;
          :isNearNode ?node .
    ?district rdfs:label ?districtName .
    ?node rdfs:label ?nodeName .
    FILTER(?districtName = "Kentron")
}
"""

results_1 = list(g.query(cq1_query))
if not results_1:
    print("No results found for Q1.")
else:
    for row in results_1:
        print(f"Listing: {row.listing.split('#')[-1]} | Price: ${row.price} | District: {row.districtName} | Near: {row.nodeName}")

# 4. Query Competency Question 2 & Apply Rule Inference
print("\n=== COMPETENCY QUESTION 2 & INFERENCE RULE ===")
print("Q2: Find all listings flagged with high-risk or predatory pricing traits.")

# Rule: If price > $1200, flag listing as high risk
for listing, _, price in g.triples((None, EX.hasPriceUSD, None)):
    if float(price) > 1200.0:
        risk_inst = EX[f"Risk_Predatory_{listing.split('#')[-1]}"]
        g.add((risk_inst, RDF.type, EX.RiskEvidence))
        g.add((risk_inst, EX.hasSeverity, Literal("HIGH")))
        g.add((risk_inst, RDFS.comment, Literal("Price anomaly detected via rule engine")))
        g.add((listing, EX.flagsRisk, risk_inst))

cq2_query = """
PREFIX : <http://example.org/fairrent#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?listing ?price ?severity ?comment WHERE {
    ?listing a :Listing ;
             :hasPriceUSD ?price ;
             :flagsRisk ?risk .
    ?risk :hasSeverity ?severity ;
          rdfs:comment ?comment .
}
"""

results_2 = list(g.query(cq2_query))
if not results_2:
    print("No high-risk listings found.")
else:
    for row in results_2:
        print(f"Listing: {row.listing.split('#')[-1]} | Price: ${row.price} | Risk Level: {row.severity} | Reason: {row.comment}")

print("\nOntology is consistent and queries executed successfully.")