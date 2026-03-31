"""
Excel generation API client.

This module handles communication with the Excel generation service.
"""

import logging
from typing import Any, Optional
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


@dataclass
class ExcelGenerationResult:
    """Result from Excel generation API."""
    success: bool
    file_url: Optional[str] = None
    file_content: Optional[bytes] = None
    error: Optional[str] = None


class ExcelClient:
    """
    Client for the Excel generation HTTP API.
    
    This client communicates with the Excel generation service
    to convert test case JSON data into formatted Excel files.
    
    Attributes:
        base_url: Excel generation API base URL
        timeout: Request timeout in seconds
    """
    
    def __init__(
        self,
        base_url: str = "http://10.31.169.36:9002",
        timeout: int = 300,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def generate_excel(
        self,
        test_cases: list[dict[str, Any]]
    ) -> ExcelGenerationResult:
        """
        Generate Excel file from test case data.
        
        Sends test case JSON to the Excel generation API and
        returns the generated file.
        
        Args:
            test_cases: List of test case dictionaries
            
        Returns:
            ExcelGenerationResult with file content or error
            
        TODO: This API endpoint needs to be implemented on the server.
        """
        url = f"{self.base_url}/generate_excel"
        
        payload = {
            "test_cases": test_cases
        }
        
        logger.info(f"Generating Excel with {len(test_cases)} test cases")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                
                if response.status_code == 200:
                    # Assuming API returns file content or URL
                    content_type = response.headers.get("Content-Type", "")
                    
                    if "application/json" in content_type:
                        data = response.json()
                        return ExcelGenerationResult(
                            success=True,
                            file_url=data.get("file_url"),
                        )
                    else:
                        # Binary file content
                        return ExcelGenerationResult(
                            success=True,
                            file_content=response.content,
                        )
                else:
                    return ExcelGenerationResult(
                        success=False,
                        error=f"API error: {response.status_code} - {response.text}",
                    )
                    
        except httpx.TimeoutException as e:
            logger.exception("Excel generation timeout")
            return ExcelGenerationResult(
                success=False,
                error=f"Timeout: {str(e)}",
            )
        except httpx.RequestError as e:
            logger.exception("Excel generation request failed")
            return ExcelGenerationResult(
                success=False,
                error=f"Request error: {str(e)}",
            )
        except Exception as e:
            logger.exception("Unexpected error in Excel generation")
            return ExcelGenerationResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
            )
    
    def generate_excel_sync(
        self,
        test_cases: list[dict[str, Any]]
    ) -> ExcelGenerationResult:
        """
        Synchronous version of generate_excel.
        
        Uses httpx sync client for non-async contexts.
        
        Args:
            test_cases: List of test case dictionaries
            
        Returns:
            ExcelGenerationResult with file content or error
        """
        url = f"{self.base_url}/generate_excel"
        
        payload = {
            "test_cases": test_cases
        }
        
        logger.info(f"Generating Excel with {len(test_cases)} test cases")
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                
                if response.status_code == 200:
                    content_type = response.headers.get("Content-Type", "")
                    
                    if "application/json" in content_type:
                        data = response.json()
                        return ExcelGenerationResult(
                            success=True,
                            file_url=data.get("file_url"),
                        )
                    else:
                        return ExcelGenerationResult(
                            success=True,
                            file_content=response.content,
                        )
                else:
                    return ExcelGenerationResult(
                        success=False,
                        error=f"API error: {response.status_code} - {response.text}",
                    )
                    
        except httpx.TimeoutException as e:
            logger.exception("Excel generation timeout")
            return ExcelGenerationResult(
                success=False,
                error=f"Timeout: {str(e)}",
            )
        except httpx.RequestError as e:
            logger.exception("Excel generation request failed")
            return ExcelGenerationResult(
                success=False,
                error=f"Request error: {str(e)}",
            )
        except Exception as e:
            logger.exception("Unexpected error in Excel generation")
            return ExcelGenerationResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
            )


# Stub implementation for when API is not available
class StubExcelClient:
    """
    Stub Excel client for development/testing.
    
    Returns mock Excel content instead of calling the API.
    """
    
    async def generate_excel(
        self,
        test_cases: list[dict[str, Any]]
    ) -> ExcelGenerationResult:
        """Return stub Excel generation result."""
        logger.warning("Using stub Excel client - no actual file generated")
        
        # Return a mock response
        return ExcelGenerationResult(
            success=True,
            file_url="http://example.com/stub_excel.xlsx",
        )
    
    def generate_excel_sync(
        self,
        test_cases: list[dict[str, Any]]
    ) -> ExcelGenerationResult:
        """Return stub Excel generation result (sync version)."""
        logger.warning("Using stub Excel client - no actual file generated")
        
        return ExcelGenerationResult(
            success=True,
            file_url="http://example.com/stub_excel.xlsx",
        )
