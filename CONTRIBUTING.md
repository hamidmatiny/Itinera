# Contributing to Itinera

Thank you for your interest in improving Itinera! This project is focused on building an AI-powered itinerary generator using FastAPI, Streamlit, and xAI Grok.

## How to contribute

1. Fork the repository and create a feature branch.
   - Use a descriptive branch name like `feature/add-share-links` or `fix/itinerary-validation`.
2. Open an issue before large changes.
   - Include a clear summary, purpose, and steps to reproduce the issue or desired enhancement.
3. Make focused, small changes.
   - One feature or fix per pull request helps reviewers move faster.

## Code style and quality

- Follow the existing project structure and naming conventions.
- Keep Python code clean and readable.
- Use type hints where appropriate.
- Prefer idiomatic FastAPI patterns in backend code.
- Keep Streamlit frontend components modular and isolated.

## Testing and validation

- Run the app locally to validate behavior:
  - `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
  - `streamlit run app.py`
- Verify route behavior, generated itinerary output, and UI flows.
- Add tests or validation steps when contributing bug fixes or new features.

## Pull request expectations

- Describe the change clearly in the PR description.
- Reference the related issue if one exists.
- Include any setup or configuration steps needed to test your change.
- Update documentation only when relevant.

## Using the screenshots folder

The `screenshots/` directory contains example guides and UI snapshots. Use it as a reference for visual expectations and design context.

## Repository topics

The following GitHub topics are recommended for this project:

- `travel`
- `itinerary`
- `grok`
- `fastapi`
- `streamlit`
- `ai-agent`

## Additional notes

If you want to help with documentation, bug fixes, or new itinerary features, please start by opening an issue so maintainers can provide guidance.
