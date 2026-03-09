"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Float } from "@react-three/drei";
import { useRef, useEffect } from "react";
import * as THREE from "three";

// Procedurally generated geometric 'Brain' placeholder mapped to a sphere
function ProceduralBrain() {
    const meshRef = useRef<THREE.Group>(null);

    // Parallax config
    const mouse = useRef({ x: 0, y: 0 });

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            // Normalize to -1 to 1
            mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1;
            mouse.current.y = -(e.clientY / window.innerHeight) * 2 + 1;
        };
        window.addEventListener("mousemove", handleMouseMove);
        return () => window.removeEventListener("mousemove", handleMouseMove);
    }, []);

    useFrame((state, delta) => {
        if (!meshRef.current) return;

        // Slow continuous rotation (1 full rotation every 15s approx)
        meshRef.current.rotation.y += delta * (Math.PI * 2 / 15);

        // Parallax tilt (±8 degrees max approx)
        const targetRotationX = mouse.current.y * 0.14;
        const targetRotationZ = -mouse.current.x * 0.14;

        // Smooth lerp towards target tilt
        meshRef.current.rotation.x += (targetRotationX - meshRef.current.rotation.x) * 0.1;
        meshRef.current.rotation.z += (targetRotationZ - meshRef.current.rotation.z) * 0.1;
    });

    return (
        <group ref={meshRef}>
            <Float speed={2} rotationIntensity={0.2} floatIntensity={0.5}>
                <mesh>
                    <icosahedronGeometry args={[2.5, 2]} />
                    <meshStandardMaterial
                        color="#111111"
                        roughness={0.7}
                        metalness={0.5}
                        wireframe={true}
                        transparent={true}
                        opacity={0.8}
                        emissive="#ffffff"
                        emissiveIntensity={0.05}
                    />
                </mesh>

                {/* Core solid structure inside */}
                <mesh scale={0.9}>
                    <octahedronGeometry args={[2.5, 4]} />
                    <meshStandardMaterial
                        color="#050505"
                        roughness={0.4}
                        metalness={0.8}
                    />
                </mesh>
            </Float>
        </group>
    );
}

export default function BrainScene() {
    return (
        <div className="w-full h-[500px] lg:h-[700px] relative pointer-events-none opacity-0 hero-brain">
            <Canvas camera={{ position: [0, 0, 7], fov: 45 }} dpr={[1, 2]}>
                {/* Soft rim lighting */}
                <ambientLight intensity={0.2} />
                <directionalLight position={[5, 5, 5]} intensity={1.5} color="#ffffff" />
                <directionalLight position={[-5, -5, -5]} intensity={0.5} color="#4facfe" />
                <spotLight position={[0, 10, 0]} intensity={2} angle={0.5} penumbra={1} color="#667eea" />

                <ProceduralBrain />
            </Canvas>
        </div>
    );
}
