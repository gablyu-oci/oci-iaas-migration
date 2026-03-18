# OCI AI and Machine Learning Services — IAM Permissions Reference

## Overview

OCI provides AI/ML services that map to AWS Bedrock, SageMaker, Comprehend, Rekognition, Textract, Polly, Transcribe, and Translate.

## Service Mapping (AWS → OCI)

| AWS Service | OCI Equivalent | Resource Type |
|---|---|---|
| Bedrock | Generative AI Service | `generative-ai-family` |
| Bedrock (custom models) | Generative AI Fine-tuning | `generative-ai-models` |
| SageMaker | Data Science | `data-science-model-deployments`, `data-science-projects` |
| Comprehend | Language (AI Language) | `ai-service-language-family` |
| Rekognition | Vision (AI Vision) | `ai-service-vision-family` |
| Textract | Document Understanding | `ai-document-family` |
| Polly | Speech (AI Speech) | `ai-service-speech-family` |
| Transcribe | AI Speech (transcription) | `ai-service-speech-family` |
| Translate | AI Language (translation) | `ai-service-language-family` |
| Forecast | AI Forecasting | `ai-forecasting-family` |
| Personalize | OCI Anomaly Detection | `ai-anomaly-detection-family` |

## Generative AI Service (generative-ai)

Maps to AWS Bedrock.

### Resource Types
- `generative-ai-family` — Group covering all Generative AI resources
- `generative-ai-endpoints` — Hosted model inference endpoints
- `generative-ai-models` — Base and fine-tuned models
- `generative-ai-dedicated-ai-clusters` — Dedicated GPU clusters

### Verbs
| Verb | Allowed Operations |
|---|---|
| `inspect` | List models, endpoints |
| `read` | Get model details, view endpoints |
| `use` | Run inference (text generation, embeddings, summarization) |
| `manage` | Create fine-tuned models, manage endpoints, allocate clusters |

### Example Policies
```
Allow group AIEngineers to manage generative-ai-family in tenancy
Allow group AppServers to use generative-ai-endpoints in compartment Production
Allow group DataScientists to read generative-ai-models in tenancy
```

## Data Science (data-science)

Maps to AWS SageMaker.

### Resource Types
- `data-science-projects` — Logical containers for ML work
- `data-science-notebook-sessions` — Jupyter notebook environments
- `data-science-models` — Trained model artifacts
- `data-science-model-deployments` — Deployed model endpoints
- `data-science-jobs` — Training jobs
- `data-science-job-runs` — Individual job executions
- `data-science-pipelines` — ML pipelines
- `data-science-pipeline-runs` — Pipeline executions
- `data-science-family` — Group resource covering all Data Science resources

### Example Policies
```
Allow group MLEngineers to manage data-science-family in compartment MLProjects
Allow group MLOps to manage data-science-model-deployments in compartment Production
Allow group DataScientists to use data-science-notebook-sessions in compartment MLProjects
```

## AI Language Service (ai-service-language)

Maps to AWS Comprehend and Translate.

### Resource Types
- `ai-service-language-family` — Group covering all Language AI resources

### Verbs
- `use` — Run language analysis (sentiment, entity detection, language detection, translation)
- `manage` — Create custom models and endpoints

### Example Policies
```
Allow group NLPApps to use ai-service-language-family in compartment Production
```

## AI Vision Service (ai-service-vision)

Maps to AWS Rekognition.

### Resource Types
- `ai-service-vision-family` — Group covering all Vision AI resources

### Verbs
- `use` — Run image analysis (object detection, face detection, text detection)
- `manage` — Create custom models

### Example Policies
```
Allow group VisionApps to use ai-service-vision-family in compartment Production
```

## AI Speech Service (ai-service-speech)

Maps to AWS Transcribe and Polly.

### Resource Types
- `ai-service-speech-family` — Group covering Speech AI resources

### Example Policies
```
Allow group SpeechApps to use ai-service-speech-family in compartment Production
```

## AI Document Understanding (ai-document)

Maps to AWS Textract.

### Resource Types
- `ai-document-family` — Document processing resources

### Example Policies
```
Allow group DocApps to use ai-document-family in compartment Production
```

## AWS → OCI IAM Action Mapping

| AWS Action | OCI Equivalent Policy |
|---|---|
| `bedrock:InvokeModel` | `use generative-ai-endpoints` |
| `bedrock:InvokeModelWithResponseStream` | `use generative-ai-endpoints` |
| `bedrock:CreateModelCustomizationJob` | `manage generative-ai-models` |
| `bedrock:GetFoundationModel` | `read generative-ai-models` |
| `bedrock:ListFoundationModels` | `inspect generative-ai-models` |
| `sagemaker:CreateTrainingJob` | `manage data-science-jobs` |
| `sagemaker:CreateEndpoint` | `manage data-science-model-deployments` |
| `sagemaker:InvokeEndpoint` | `use data-science-model-deployments` |
| `sagemaker:CreateNotebookInstance` | `manage data-science-notebook-sessions` |
| `comprehend:DetectEntities` | `use ai-service-language-family` |
| `comprehend:DetectSentiment` | `use ai-service-language-family` |
| `rekognition:DetectLabels` | `use ai-service-vision-family` |
| `rekognition:DetectFaces` | `use ai-service-vision-family` |
| `transcribe:StartTranscriptionJob` | `use ai-service-speech-family` |
| `textract:AnalyzeDocument` | `use ai-document-family` |
| `translate:TranslateText` | `use ai-service-language-family` |
