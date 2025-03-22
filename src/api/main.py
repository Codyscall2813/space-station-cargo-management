from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from src.db.session import engine, Base
from src.models import *

# Initialize FastAPI app
app = FastAPI(
    title="Space Station Cargo Management System",
    description="API for optimizing storage operations aboard space vessels",
    version="1.0.0"
)

# Add CORS middleware to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the actual origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables if they don't exist
@app.on_event("startup")
async def startup_db_client():
    Base.metadata.create_all(bind=engine)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Welcome to the Space Station Cargo Management System API",
        "documentation": "/docs",
        "version": "1.0.0"
    }

# Import route modules
from src.api.routes import placement, retrieval, simulation, waste_management, import_export, logs

# Include routers
app.include_router(placement.router, prefix="/api", tags=["Placement"])
app.include_router(retrieval.router, prefix="/api", tags=["Retrieval"])
app.include_router(simulation.router, prefix="/api", tags=["Simulation"])
app.include_router(waste_management.router, prefix="/api/waste", tags=["Waste Management"])
app.include_router(import_export.router, prefix="/api", tags=["Import/Export"])
app.include_router(logs.router, prefix="/api", tags=["Logs"])
