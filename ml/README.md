# ML

Median baseline, rental price model, prediction intervals, and evaluation. Start with the data contract. Keep duplicate groups from crossing training/test boundaries.

Lazar owns model implementation and evaluation. Mane coordinates security checks for model inputs and trusted artifact integrity (E03–E04); this does not transfer model or AWS/IAM ownership.

Stack: pandas, scikit-learn, and CatBoost; model artifacts stored in S3. See the [technology stack](../docs/technology-stack.md).
